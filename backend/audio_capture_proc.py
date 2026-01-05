from __future__ import annotations

import sys
import time
import queue
from typing import Union, Tuple

import numpy as np
import sounddevice as sd
from multiprocessing.connection import Client


# IPC message protocol to parent:
# ("pcm", ts:float, rms:float, pcm_bytes:bytes)
# ("log", text:str)
# ("err", text:str)

def _to_mono_int16_left(indata: np.ndarray) -> Tuple[bytes, float]:
    """
    Convert sounddevice callback 'indata' into mono PCM16 little-endian bytes.
    Uses LEFT channel only (avoids phase-cancellation artifacts from stereo system audio).
    Returns (pcm_bytes, rms_float_0_1).
    """
    x = np.asarray(indata)

    # Choose mono signal
    if x.ndim == 2 and x.shape[1] >= 1:
        mono = x[:, 0]  # LEFT channel only
    else:
        mono = x.reshape(-1)

    # Convert to float32 in [-1, 1] for consistent scaling/rms
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
    Audio-capture process:
      - Opens sounddevice InputStream
      - Downmixes to mono int16 @ sample_rate
      - Sends frames over IPC to parent
    """
    conn = Client((host, port), authkey=b"shadowcoach")

    def send(kind: str, payload):
        try:
            conn.send((kind, payload))
        except Exception:
            pass

    send("log", f"capture start device={device} sr={sample_rate} ch={channels} bs={blocksize}")

    # Buffer a little; drop oldest when behind to keep latency down
    q: "queue.Queue[tuple[float, float, bytes]]" = queue.Queue(maxsize=250)

    def audio_cb(indata, frames, time_info, status):
        if status:
            send("log", f"sd_status: {status}")

        try:
            pcm16, rms = _to_mono_int16_left(indata)
            ts = time.time()

            if q.full():
                try:
                    q.get_nowait()
                except Exception:
                    pass
            q.put_nowait((ts, rms, pcm16))
        except Exception as e:
            send("err", f"cb_error: {repr(e)}")

        # Yield helps scheduling on Windows; safe even in child
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
                    # Keepalive
                    send("log", "keepalive")
    except Exception as e:
        send("err", f"stream_error: {repr(e)}")
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--device", required=True)
    p.add_argument("--sr", type=int, default=48000)
    p.add_argument("--ch", type=int, default=2)
    p.add_argument("--bs", type=int, default=960)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, required=True)
    args = p.parse_args()

    dev = int(args.device) if args.device.isdigit() else args.device
    run_capture_proc(dev, args.sr, args.ch, args.bs, args.host, args.port)
