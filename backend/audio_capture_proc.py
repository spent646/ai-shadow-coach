from __future__ import annotations

import sys
import time
import queue
from typing import Union, Tuple

import numpy as np
import sounddevice as sd
from multiprocessing.connection import Client


def _to_mono_int16_left(indata: np.ndarray) -> Tuple[bytes, float]:
    """
    Convert callback indata -> mono PCM16 LE bytes (LEFT channel only).
    Returns (pcm_bytes, rms_0_1).
    """
    x = np.asarray(indata)

    if x.ndim == 2 and x.shape[1] >= 1:
        mono = x[:, 0]  # LEFT only
    else:
        mono = x.reshape(-1)

    if mono.dtype == np.int16:
        f = mono.astype(np.float32) / 32768.0
    else:
        f = mono.astype(np.float32)

    f = np.clip(f, -1.0, 1.0)
    pcm16 = (f * 32767.0).astype(np.int16).tobytes(order="C")
    rms = float(np.sqrt(np.mean(f * f)) + 1e-12)
    return pcm16, rms


def run_capture_proc(
    device: Union[int, str],
    sample_rate: int = 48000,
    channels: int = 2,
    blocksize: int = 960,
    host: str = "127.0.0.1",
    port: int = 0,
):
    """
    Separate process: opens sounddevice InputStream and sends PCM frames via multiprocessing connection.
    Messages:
      ("pcm", ts, rms, pcm16_bytes)
      ("log", text)
      ("err", text)
    """
    conn = Client((host, port), authkey=b"shadowcoach")

    def send(kind: str, payload):
        try:
            conn.send((kind, payload))
        except Exception:
            pass

    # normalize device index if it's numeric-as-string
    try:
        if isinstance(device, str) and device.lstrip("-").isdigit():
            device = int(device)
    except Exception:
        pass

    send("log", f"capture start device={device} sr={sample_rate} ch={channels} bs={blocksize}")
    send("log", f"opening device={device} sr={sample_rate} ch={channels} bs={blocksize}")

    q: "queue.Queue[tuple[float, float, bytes]]" = queue.Queue(maxsize=250)

    def audio_cb(indata, frames, time_info, status):
        if status:
            send("log", f"sd_status: {status}")

        try:
            pcm16, rms = _to_mono_int16_left(indata)
            ts = time.time()

            # Keep latest audio; drop oldest when behind
            if q.full():
                try:
                    q.get_nowait()
                except Exception:
                    pass

            q.put_nowait((ts, rms, pcm16))
        except Exception as e:
            send("err", f"cb_error: {repr(e)}")

        # Helps Windows scheduler fairness
        if sys.platform == "win32":
            time.sleep(0)

    try:
        with sd.InputStream(
            device=device,
            samplerate=int(sample_rate),
            channels=int(channels),
            dtype="float32",
            blocksize=int(blocksize),
            callback=audio_cb,
        ):
            while True:
                try:
                    ts, rms, pcm16 = q.get(timeout=0.5)
                    try:
                        conn.send(("pcm", ts, rms, pcm16))
                    except (BrokenPipeError, ConnectionResetError, EOFError):
                        break
                except queue.Empty:
                    send("log", "keepalive")
    except Exception as e:
        send("err", f"stream_error: {repr(e)}")
    finally:
        try:
            conn.close()
        except Exception:
            pass
