from __future__ import annotations

import asyncio
import json
import os
import queue
import sys
import time
import threading
import multiprocessing as mp
from dataclasses import dataclass
from typing import Callable, Optional, Dict, Any, Tuple

import aiohttp
from multiprocessing.connection import Listener

# IMPORTANT: sounddevice is ONLY used in the capture subprocess now.
# This avoids Windows GIL starvation between PortAudio callbacks and websocket send/recv.
from audio_capture_proc import run_capture_proc

def list_audio_devices():
    """
    Returns available INPUT audio devices.
    This is used by main.py / UI for device selection.
    """
    import sounddevice as sd

    devices = []
    try:
        for idx, d in enumerate(sd.query_devices()):
            if int(d.get("max_input_channels", 0)) <= 0:
                continue

            devices.append(
                {
                    "index": idx,
                    "name": d.get("name", f"Device {idx}"),
                    "max_input_channels": int(d.get("max_input_channels", 0)),
                    "default_samplerate": int(d.get("default_samplerate", 0) or 0),
                }
            )
    except Exception as e:
        return {
            "ok": False,
            "error": repr(e),
            "devices": [],
        }

    return {
        "ok": True,
        "devices": devices,
    }

DEEPGRAM_URL_BASE = (
    "wss://api.deepgram.com/v1/listen"
    "?model=nova-2"
    "&punctuate=true"
    "&smart_format=true"
    "&encoding=linear16"
    "&channels=1"
    "&interim_results=true"
    "&utterance_end_ms=1000"
    "&endpointing=200"
    "&vad_events=true"
)

MAX_BATCH = 32


def build_deepgram_url(sample_rate: int) -> str:
    sr = int(sample_rate) if sample_rate else 48000
    return f"{DEEPGRAM_URL_BASE}&sample_rate={sr}"


@dataclass
class StreamConfig:
    device_index: int
    label: str          # "mic" or "vm"
    speaker: str        # "A" or "B"
    sample_rate: int = 48000
    blocksize: int = 960   # ~20ms @ 48k
    channels: int = 2      # capture in stereo; downmix in child using LEFT channel only


# -------------------- Worker Process (Deepgram + IPC receiver) --------------------

def _stream_worker_process(
    cfg: StreamConfig,
    deepgram_key: str,
    stop_evt: "mp.Event",
    status_q: "mp.Queue[Dict[str, Any]]",
    text_q: "mp.Queue[Dict[str, str]]",
):
    """
    One process per stream:
      - Spawns a CAPTURE subprocess that runs sounddevice and sends PCM frames over IPC
      - This worker process runs Deepgram websocket + receives PCM via IPC
      - Emits transcript events to parent via text_q
      - Pushes health/status snapshots to parent via status_q
    This fully decouples PortAudio callbacks from websocket + asyncio on Windows.
    """

    # Local (in-process) queue of PCM16 chunks (from capture proc)
    q: "queue.Queue[bytes]" = queue.Queue(maxsize=2000)

    # Stats
    level = 0.0
    queue_drops = 0
    bytes_sent = 0
    msgs_recv = 0
    emit_count = 0
    last_partial = ""
    last_final = ""
    last_emit_text = ""
    last_dg_type = ""
    last_dg_error = ""
    last_ws_close = ""
    last_capture_log = ""
    last_capture_err = ""
    last_dg_raw = ""
    last_dg_no_transcript = 0

    last_audio_ts = 0.0
    last_send_ts = 0.0
    last_recv_ts = 0.0
    last_emit_ts = 0.0

    # Backpressure settings inside worker
    q_soft_cap = 200  # keep WS live; drop oldest if behind

    # Capture proc plumbing
    ctx = mp.get_context("spawn")
    listener: Optional[Listener] = None
    conn = None
    cap_proc: Optional[mp.Process] = None
    ipc_connected = False

    def push_status(extra: Optional[Dict[str, Any]] = None):
        nonlocal level, queue_drops, bytes_sent, msgs_recv, emit_count
        nonlocal last_partial, last_final, last_emit_text, last_dg_type, last_dg_error, last_ws_close
        nonlocal last_capture_log, last_capture_err, last_dg_raw, last_dg_no_transcript
        nonlocal last_audio_ts, last_send_ts, last_recv_ts, ipc_connected, cap_proc

        now = time.time()
        payload = {
            "ts": now,
            "status": "streaming",
            "rms": float(level),
            "partial": last_partial,
            "final": last_final,
            "emit_count": int(emit_count),
            "bytes_sent": int(bytes_sent),
            "msgs_recv": int(msgs_recv),
            "queue_drops": int(queue_drops),
            "queue_size": int(q.qsize()),
            "last_emit_text": last_emit_text,
            "last_dg_type": last_dg_type,
            "last_dg_error": last_dg_error,
            "last_ws_close": last_ws_close,
            "audio_age_ms": int((now - last_audio_ts) * 1000) if last_audio_ts else None,
            "send_age_ms": int((now - last_send_ts) * 1000) if last_send_ts else None,
            "recv_age_ms": int((now - last_recv_ts) * 1000) if last_recv_ts else None,
            "capture_alive": bool(cap_proc.is_alive()) if cap_proc else False,
            "ipc_connected": bool(ipc_connected),
            "capture_last_log": last_capture_log,
            "capture_last_err": last_capture_err,
            "last_dg_raw": last_dg_raw,
            "last_dg_no_transcript": int(last_dg_no_transcript),
        }
        if extra:
            payload.update(extra)
        try:
            status_q.put_nowait(payload)
        except Exception:
            pass

    def emit_text(text: str):
        nonlocal emit_count, last_emit_text, last_emit_ts
        t = (text or "").strip()
        if not t:
            return
        emit_count += 1
        last_emit_text = t
        last_emit_ts = time.time()
        try:
            text_q.put_nowait({"speaker": cfg.speaker, "text": t})
        except Exception:
            pass

    def start_capture_proc() -> Tuple[Listener, mp.Process]:
        nonlocal listener, cap_proc, ipc_connected
        listener = Listener(("127.0.0.1", 0), authkey=b"shadowcoach")
        host, port = listener.address
        cap_proc = ctx.Process(
            target=run_capture_proc,
            args=(cfg.device_index, cfg.sample_rate, cfg.channels, cfg.blocksize, host, port),
            daemon=True,
        )
        cap_proc.start()
        ipc_connected = False
        return listener, cap_proc

    async def ipc_reader():
        """
        Receive ("pcm", ts, rms, bytes) from capture proc and push into q.
        """
        nonlocal conn, ipc_connected, level, last_audio_ts, last_capture_log, last_capture_err, queue_drops
        # Accept connection (blocking) in a thread so asyncio loop stays responsive.
        def _accept():
            return listener.accept()

        conn = await asyncio.get_running_loop().run_in_executor(None, _accept)
        ipc_connected = True

        while not stop_evt.is_set():
            # poll with small timeout to allow cancellation
            try:
                if conn.poll(0.1):
                    msg = conn.recv()
                else:
                    await asyncio.sleep(0.01)
                    continue
            except (EOFError, BrokenPipeError, ConnectionResetError):
                ipc_connected = False
                break
            except Exception as e:
                last_capture_err = f"ipc_recv_error: {repr(e)}"
                ipc_connected = False
                break

            try:
                kind = msg[0]
            except Exception:
                continue

            if kind == "pcm":
                _, ts, rms, pcm16 = msg
                last_audio_ts = float(ts)
                level = float(rms)

                # backpressure: drop oldest if behind to keep audio current
                try:
                    if q.qsize() >= q_soft_cap:
                        try:
                            _ = q.get_nowait()
                        except queue.Empty:
                            pass
                        queue_drops += 1
                    q.put_nowait(pcm16)
                except queue.Full:
                    queue_drops += 1

            elif kind == "log":
                _, text = msg
                last_capture_log = str(text)[:300]
            elif kind == "err":
                _, text = msg
                last_capture_err = str(text)[:300]

    async def dg_loop():
        nonlocal bytes_sent, msgs_recv, last_send_ts, last_recv_ts
        nonlocal last_partial, last_final, last_dg_type, last_dg_error, last_ws_close
        nonlocal last_dg_raw, last_dg_no_transcript

        url = build_deepgram_url(cfg.sample_rate)
        headers = {"Authorization": f"Token {deepgram_key}"}

        timeout = aiohttp.ClientTimeout(total=None)
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.ws_connect(url, heartbeat=20) as ws:

                async def sender():
                    nonlocal bytes_sent, last_send_ts
                    while not stop_evt.is_set():
                        batch = []
                        for _ in range(MAX_BATCH):
                            try:
                                batch.append(q.get_nowait())
                            except queue.Empty:
                                break

                        if not batch:
                            await asyncio.sleep(0.005)
                            continue

                        for chunk in batch:
                            await ws.send_bytes(chunk)
                            bytes_sent += len(chunk)
                            last_send_ts = time.time()

                async def receiver():
                    nonlocal msgs_recv, last_recv_ts
                    nonlocal last_partial, last_final, last_dg_type, last_dg_error, last_ws_close
                    nonlocal last_dg_raw, last_dg_no_transcript

                    while not stop_evt.is_set():
                        msg = await ws.receive()

                        if msg.type == aiohttp.WSMsgType.CLOSED:
                            raise RuntimeError("WebSocket closed")
                        if msg.type == aiohttp.WSMsgType.ERROR:
                            raise RuntimeError(f"WebSocket error: {ws.exception()}")

                        if msg.type != aiohttp.WSMsgType.TEXT:
                            continue

                        msgs_recv += 1
                        last_recv_ts = time.time()

                        raw = msg.data
                        # keep a small rolling sample
                        last_dg_raw = (raw[:600] if isinstance(raw, str) else str(raw)[:600])

                        try:
                            data = json.loads(raw)
                        except Exception:
                            continue
                        if not isinstance(data, dict):
                            continue

                        msg_type = str(data.get("type") or "")
                        if msg_type:
                            last_dg_type = msg_type

                        if "error" in data or msg_type.lower() == "error":
                            last_dg_error = json.dumps(data)[:800]

                        # Extract transcript
                        transcript = ""
                        chan = data.get("channel")
                        if isinstance(chan, dict):
                            alts = chan.get("alternatives")
                            if isinstance(alts, list) and alts and isinstance(alts[0], dict):
                                transcript = (alts[0].get("transcript") or "").strip()

                        if not transcript:
                            last_dg_no_transcript += 1
                            continue

                        is_final = bool(data.get("is_final"))
                        speech_final = bool(data.get("speech_final"))
                        utterance_end = (msg_type.lower() == "utteranceend")
                        force_commit = is_final or speech_final or utterance_end

                        if force_commit:
                            last_final = transcript
                            last_partial = ""
                            emit_text(transcript)
                        else:
                            last_partial = transcript

                            # Partial emit rule
                            now = time.time()
                            last = last_emit_text
                            has_audio = level > 0.01  # RMS scale 0..1

                            grew = len(transcript) >= max(8, len(last) + 6) and transcript != last
                            time_ready = (now - last_emit_ts) > 1.0

                            identical = (transcript == last)
                            dup_cooldown_ok = (now - last_emit_ts) > 2.0

                            if has_audio and (grew or (time_ready and (not identical or dup_cooldown_ok))):
                                emit_text(transcript)

                async def status_pumper():
                    while not stop_evt.is_set():
                        push_status()
                        await asyncio.sleep(0.5)

                tasks = [
                    asyncio.create_task(sender()),
                    asyncio.create_task(receiver()),
                    asyncio.create_task(status_pumper()),
                ]
                done, pending = await asyncio.wait(set(tasks), return_when=asyncio.FIRST_EXCEPTION)
                for t in pending:
                    t.cancel()
                for t in done:
                    exc = t.exception()
                    if exc:
                        raise exc

    # Run worker
    try:
        push_status({"status": "starting"})
        start_capture_proc()

        # Dedicated loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        backoff = 0.5
        while not stop_evt.is_set():
            try:
                last_ws_close = ""
                push_status({"status": "connecting"})

                # Start IPC reader + Deepgram concurrently
                tasks = [
                    loop.create_task(ipc_reader()),
                    loop.create_task(dg_loop()),
                ]
                done, pending = loop.run_until_complete(asyncio.wait(set(tasks), return_when=asyncio.FIRST_EXCEPTION))
                for t in pending:
                    t.cancel()
                for t in done:
                    exc = t.exception()
                    if exc:
                        raise exc

                backoff = 0.5
            except Exception as e:
                last_ws_close = repr(e)
                push_status({"status": "ws_error", "last_ws_close": last_ws_close})

                # If IPC died, restart capture proc
                try:
                    if cap_proc and cap_proc.is_alive():
                        cap_proc.terminate()
                except Exception:
                    pass
                try:
                    if listener:
                        listener.close()
                except Exception:
                    pass
                time.sleep(0.2)
                try:
                    start_capture_proc()
                except Exception as e2:
                    last_capture_err = f"restart_capture_failed: {repr(e2)}"

                time.sleep(backoff)
                backoff = min(5.0, backoff * 1.7)

        # shutdown
        try:
            if cap_proc and cap_proc.is_alive():
                cap_proc.terminate()
        except Exception:
            pass
        try:
            if conn:
                conn.close()
        except Exception:
            pass
        try:
            if listener:
                listener.close()
        except Exception:
            pass

        try:
            loop.stop()
            loop.close()
        except Exception:
            pass

    except Exception as e:
        push_status({"status": "audio_error", "capture_error": repr(e)})

    push_status({"status": "stopped"})


# -------------------- Parent-side Controller --------------------

class ProcessStreamController:
    """
    Parent-side wrapper around a worker process.
    If the worker freezes (send/recv age grows while audio is active),
    parent terminates & restarts the process.
    """

    def __init__(self, cfg: StreamConfig, deepgram_key: str, on_text: Callable[[str, str], None]):
        self.cfg = cfg
        self.deepgram_key = deepgram_key
        self.on_text = on_text

        self._ctx = mp.get_context("spawn")
        self._stop = self._ctx.Event()
        self._status_q: "mp.Queue[Dict[str, Any]]" = self._ctx.Queue(maxsize=200)
        self._text_q: "mp.Queue[Dict[str, str]]" = self._ctx.Queue(maxsize=500)
        self._proc: Optional[mp.Process] = None

        self._stop_threads = threading.Event()
        self._pump_thread: Optional[threading.Thread] = None
        self._monitor_thread: Optional[threading.Thread] = None

        # Latest status snapshot exposed to /audio/status
        self.latest: Dict[str, Any] = {
            "status": "stopped",
            "rms": 0.0,
            "partial": "",
            "final": "",
            "emit_count": 0,
            "bytes_sent": 0,
            "msgs_recv": 0,
            "queue_drops": 0,
            "queue_size": 0,
            "last_emit_text": "",
            "last_dg_type": "",
            "last_dg_error": "",
            "last_ws_close": "",
            "audio_age_ms": None,
            "send_age_ms": None,
            "recv_age_ms": None,
            "capture_alive": False,
            "ipc_connected": False,
            "capture_last_log": "",
            "capture_last_err": "",
            "last_dg_raw": "",
            "last_dg_no_transcript": 0,
            "capture_error": "",
        }

        # Freeze detection thresholds
        self._freeze_ms = 12_000      # if send/recv age exceeds this...
        self._freeze_audio_ms = 1500  # ...while audio is active (age < this)
        self._freeze_queue_min = 5    # ...and there's queued audio

    def start(self):
        self.stop()  # hard reset any old one

        self._stop.clear()
        self._stop_threads.clear()

        self._proc = self._ctx.Process(
            target=_stream_worker_process,
            args=(self.cfg, self.deepgram_key, self._stop, self._status_q, self._text_q),
            daemon=True,
        )
        self._proc.start()

        self._pump_thread = threading.Thread(target=self._pump_loop, daemon=True)
        self._pump_thread.start()

        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

    def stop(self):
        self._stop_threads.set()
        try:
            self._stop.set()
        except Exception:
            pass

        if self._proc and self._proc.is_alive():
            try:
                self._proc.terminate()
            except Exception:
                pass

        self._proc = None
        self.latest["status"] = "stopped"

    def _pump_loop(self):
        # Move text + status from queues into parent state
        while not self._stop_threads.is_set():
            # status
            try:
                while True:
                    s = self._status_q.get_nowait()
                    for k, v in s.items():
                        if k == "ts":
                            continue
                        self.latest[k] = v
            except Exception:
                pass

            # text
            try:
                while True:
                    t = self._text_q.get_nowait()
                    sp = t.get("speaker", "")
                    txt = t.get("text", "")
                    if sp and txt:
                        self.on_text(sp, txt)
            except Exception:
                pass

            time.sleep(0.05)

    def _monitor_loop(self):
        # If worker freezes, kill/restart it
        while not self._stop_threads.is_set():
            st = self.latest

            try:
                audio_age = st.get("audio_age_ms")
                send_age = st.get("send_age_ms")
                recv_age = st.get("recv_age_ms")
                qsz = st.get("queue_size", 0)
                status = (st.get("status") or "").lower()

                frozen = False
                if status in ("streaming", "connecting", "ws_error"):
                    if audio_age is not None and audio_age < self._freeze_audio_ms and qsz >= self._freeze_queue_min:
                        if (send_age is not None and send_age > self._freeze_ms) or (recv_age is not None and recv_age > self._freeze_ms):
                            frozen = True

                if frozen:
                    st["last_ws_close"] = f"ParentRestart: frozen (send_age={send_age}, recv_age={recv_age}, q={qsz})"
                    self.stop()
                    time.sleep(0.5)
                    self.start()
                    time.sleep(1.0)
                    continue

            except Exception:
                pass

            time.sleep(0.5)


class DualAudioController:
    def __init__(self, on_text: Callable[[str, str], None]):
        dg_key = os.getenv("DEEPGRAM_API_KEY", "").strip()
        if not dg_key:
            raise RuntimeError("Missing DEEPGRAM_API_KEY in environment/.env")
        self._dg_key = dg_key
        self._on_text = on_text

        self.mic_ctrl: Optional[ProcessStreamController] = None
        self.vm_ctrl: Optional[ProcessStreamController] = None

    def start(self, mic_device_index: int, vm_device_index: int):
        mic_cfg = StreamConfig(
            device_index=mic_device_index,
            label="mic",
            speaker="A",
            sample_rate=48000,
            blocksize=960,
            channels=2,
        )
        vm_cfg = StreamConfig(
            device_index=vm_device_index,
            label="vm",
            speaker="B",
            sample_rate=48000,
            blocksize=960,
            channels=2,
        )

        self.mic_ctrl = ProcessStreamController(mic_cfg, self._dg_key, self._on_text)
        self.vm_ctrl = ProcessStreamController(vm_cfg, self._dg_key, self._on_text)

        self.mic_ctrl.start()
        self.vm_ctrl.start()

    def stop(self):
        if self.mic_ctrl:
            self.mic_ctrl.stop()
        if self.vm_ctrl:
            self.vm_ctrl.stop()

    def status(self):
        def pack(ctrl: Optional[ProcessStreamController]):
            if not ctrl:
                return {
                    "status": "stopped",
                    "rms": 0.0,
                    "partial": "",
                    "final": "",
                    "emit_count": 0,
                    "bytes_sent": 0,
                    "msgs_recv": 0,
                    "queue_drops": 0,
                    "queue_size": 0,
                    "last_emit_text": "",
                    "last_dg_type": "",
                    "last_dg_error": "",
                    "last_ws_close": "",
                    "audio_age_ms": None,
                    "send_age_ms": None,
                    "recv_age_ms": None,
                    "capture_alive": False,
                    "ipc_connected": False,
                    "capture_last_log": "",
                    "capture_last_err": "",
                    "last_dg_raw": "",
                    "last_dg_no_transcript": 0,
                    "capture_error": "",
                }
            base = {
                "status": "stopped",
                "rms": 0.0,
                "partial": "",
                "final": "",
                "emit_count": 0,
                "bytes_sent": 0,
                "msgs_recv": 0,
                "queue_drops": 0,
                "queue_size": 0,
                "last_emit_text": "",
                "last_dg_type": "",
                "last_dg_error": "",
                "last_ws_close": "",
                "audio_age_ms": None,
                "send_age_ms": None,
                "recv_age_ms": None,
                "capture_alive": False,
                "ipc_connected": False,
                "capture_last_log": "",
                "capture_last_err": "",
                "last_dg_raw": "",
                "last_dg_no_transcript": 0,
                "capture_error": "",
            }
            base.update(ctrl.latest or {})
            return base

        return {"mic": pack(self.mic_ctrl), "vm": pack(self.vm_ctrl)}
