from __future__ import annotations

import asyncio
import json
import os
import queue
import threading
import time
import multiprocessing as mp
from dataclasses import dataclass
from typing import Callable, Optional, Dict, Any

import aiohttp
from multiprocessing.connection import Listener

from audio_capture_proc import run_capture_proc


def list_audio_devices():
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
        return {"ok": False, "error": repr(e), "devices": []}

    return {"ok": True, "devices": devices}


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


def build_deepgram_url(sample_rate: int) -> str:
    sr = int(sample_rate) if sample_rate else 48000
    return f"{DEEPGRAM_URL_BASE}&sample_rate={sr}"


@dataclass
class StreamConfig:
    device_index: int
    label: str
    speaker: str
    sample_rate: int = 48000
    blocksize: int = 960
    channels: int = 2


def _stream_worker_process(
    cfg: StreamConfig,
    deepgram_key: str,
    stop_evt: "mp.Event",
    status_q: "mp.Queue[Dict[str, Any]]",
    text_q: "mp.Queue[Dict[str, str]]",
):
    pcm_q: "queue.Queue[bytes]" = queue.Queue(maxsize=2000)

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

    q_soft_cap = 200

    ctx = mp.get_context("spawn")
    listener: Optional[Listener] = None
    conn = None
    cap_proc: Optional[mp.Process] = None
    ipc_connected = False

    def push_status(extra: Optional[Dict[str, Any]] = None):
        nonlocal ipc_connected, cap_proc
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
            "queue_size": int(pcm_q.qsize()),
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

    def start_capture_proc():
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

    async def ipc_reader():
        nonlocal conn, ipc_connected, level, last_audio_ts, last_capture_log, last_capture_err, queue_drops
        assert listener is not None

        def _accept():
            return listener.accept()

        try:
            conn = await asyncio.get_running_loop().run_in_executor(None, _accept)
            ipc_connected = True
        except Exception as e:
            last_capture_err = f"ipc_accept_error: {repr(e)}"
            ipc_connected = False
            return

        while not stop_evt.is_set():
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

                if pcm_q.qsize() >= q_soft_cap:
                    try:
                        _ = pcm_q.get_nowait()
                        queue_drops += 1
                    except queue.Empty:
                        pass

                try:
                    pcm_q.put_nowait(pcm16)
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
                    frames_per_chunk = int(cfg.blocksize)
                    sr = int(cfg.sample_rate)
                    chunk_seconds = frames_per_chunk / float(sr)

                    next_send_time = time.time()

                    while not stop_evt.is_set():
                        try:
                            chunk = pcm_q.get_nowait()
                        except queue.Empty:
                            await asyncio.sleep(0.001)
                            continue

                        await ws.send_bytes(chunk)
                        bytes_sent += len(chunk)
                        last_send_ts = time.time()

                        next_send_time += chunk_seconds
                        now = time.time()
                        delay = next_send_time - now
                        if delay > 0:
                            await asyncio.sleep(delay)
                        else:
                            next_send_time = now

                async def receiver():
                    nonlocal msgs_recv, last_recv_ts
                    nonlocal last_partial, last_final, last_dg_type, last_dg_error, last_ws_close
                    nonlocal last_dg_raw, last_dg_no_transcript

                    while not stop_evt.is_set():
                        msg = await ws.receive()

                        if msg.type == aiohttp.WSMsgType.CLOSED:
                            last_ws_close = f"WebSocket closed code={ws.close_code}"
                            raise RuntimeError(last_ws_close)
                        if msg.type == aiohttp.WSMsgType.ERROR:
                            last_ws_close = f"WebSocket error: {ws.exception()}"
                            raise RuntimeError(last_ws_close)

                        if msg.type != aiohttp.WSMsgType.TEXT:
                            continue

                        msgs_recv += 1
                        last_recv_ts = time.time()

                        raw = msg.data
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

    loop: Optional[asyncio.AbstractEventLoop] = None
    try:
        push_status({"status": "starting"})
        start_capture_proc()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        ipc_task = loop.create_task(ipc_reader())

        t0 = time.time()
        while not ipc_connected and (time.time() - t0) < 2.0 and not stop_evt.is_set():
            loop.run_until_complete(asyncio.sleep(0.05))

        backoff = 0.5
        while not stop_evt.is_set():
            try:
                push_status({"status": "connecting"})
                loop.run_until_complete(dg_loop())
                backoff = 0.5
            except Exception as e:
                last_ws_close = repr(e)
                push_status({"status": "ws_error", "last_ws_close": last_ws_close})
                time.sleep(backoff)
                backoff = min(5.0, backoff * 1.7)

        if not ipc_task.done():
            ipc_task.cancel()

    except Exception as e:
        push_status({"status": "audio_error", "capture_error": repr(e)})

    finally:
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
            if loop:
                loop.stop()
                loop.close()
        except Exception:
            pass

        push_status({"status": "stopped"})


class ProcessStreamController:
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
            # NEW parent-side fields
            "worker_pid": None,
            "worker_alive": False,
            "worker_exitcode": None,
        }

    def start(self):
        self.stop()
        self.latest["status"] = "starting"
        self.latest["capture_error"] = ""
        self.latest["worker_pid"] = None
        self.latest["worker_alive"] = False
        self.latest["worker_exitcode"] = None

        self._stop.clear()
        self._stop_threads.clear()

        self._proc = self._ctx.Process(
            target=_stream_worker_process,
            args=(self.cfg, self.deepgram_key, self._stop, self._status_q, self._text_q),
            daemon=False,
        )
        self._proc.start()

        # record immediately
        self.latest["worker_pid"] = self._proc.pid
        self.latest["worker_alive"] = self._proc.is_alive()
        self.latest["worker_exitcode"] = self._proc.exitcode

        self._pump_thread = threading.Thread(target=self._pump_loop, daemon=True)
        self._pump_thread.start()

    def stop(self):
        self._stop_threads.set()
        try:
            self._stop.set()
        except Exception:
            pass

        if self._proc and self._proc.is_alive():
            try:
                self._proc.terminate()
                self._proc.join(timeout=1.5)
            except Exception:
                pass

        self._proc = None
        self.latest["status"] = "stopped"
        self.latest["worker_alive"] = False
        self.latest["worker_exitcode"] = None
        self.latest["worker_pid"] = None

    def _pump_loop(self):
        while not self._stop_threads.is_set():
            # Update parent-side process health every tick
            if self._proc:
                self.latest["worker_pid"] = self._proc.pid
                self.latest["worker_alive"] = self._proc.is_alive()
                self.latest["worker_exitcode"] = self._proc.exitcode

                # If process died, surface it hard
                if (not self._proc.is_alive()) and self._proc.exitcode is not None:
                    self.latest["status"] = "audio_error"
                    self.latest["capture_error"] = f"worker_exitcode={self._proc.exitcode}"

            try:
                while True:
                    s = self._status_q.get_nowait()
                    for k, v in s.items():
                        if k != "ts":
                            self.latest[k] = v
            except Exception:
                pass

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
        mic_cfg = StreamConfig(device_index=mic_device_index, label="mic", speaker="A")
        vm_cfg = StreamConfig(device_index=vm_device_index, label="vm", speaker="B")

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
        def empty():
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
                "worker_pid": None,
                "worker_alive": False,
                "worker_exitcode": None,
            }

        mic = empty()
        vm = empty()

        if self.mic_ctrl:
            mic.update(self.mic_ctrl.latest or {})
            # force refresh process health (even if pump thread never ran)
            if self.mic_ctrl._proc:
                mic["worker_pid"] = self.mic_ctrl._proc.pid
                mic["worker_alive"] = self.mic_ctrl._proc.is_alive()
                mic["worker_exitcode"] = self.mic_ctrl._proc.exitcode
                if (not mic["worker_alive"]) and mic["worker_exitcode"] is not None and mic["status"] == "starting":
                    mic["status"] = "audio_error"
                    mic["capture_error"] = f"worker_exitcode={mic['worker_exitcode']}"

        if self.vm_ctrl:
            vm.update(self.vm_ctrl.latest or {})
            if self.vm_ctrl._proc:
                vm["worker_pid"] = self.vm_ctrl._proc.pid
                vm["worker_alive"] = self.vm_ctrl._proc.is_alive()
                vm["worker_exitcode"] = self.vm_ctrl._proc.exitcode
                if (not vm["worker_alive"]) and vm["worker_exitcode"] is not None and vm["status"] == "starting":
                    vm["status"] = "audio_error"
                    vm["capture_error"] = f"worker_exitcode={vm['worker_exitcode']}"

        return {"mic": mic, "vm": vm}
