from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Optional, Any, Dict, List

# ✅ Windows multiprocessing hardening (must be top-level, before spawning)
import multiprocessing as mp

try:
    mp.freeze_support()
except Exception:
    pass

try:
    mp.set_start_method("spawn", force=True)
except Exception:
    pass

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from audio_dual import DualAudioController, list_audio_devices

load_dotenv()

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

LOCK = threading.Lock()

# --- optional integration with your existing coach/state modules ---
try:
    from state import STATE, Turn  # type: ignore
except Exception:
    STATE = type("STATE", (), {})()
    STATE.turns = []
    STATE.last_coach = {}
    STATE.topic = ""
    STATE.scope = ""
    Turn = None  # type: ignore

try:
    from coach import generate_coach  # type: ignore
except Exception:
    generate_coach = None  # type: ignore


class AddLineReq(BaseModel):
    speaker: str
    text: str


class AudioStartReq(BaseModel):
    mic_device_index: Optional[int] = None
    vm_device_index: Optional[int] = None


def _append_turn(speaker: str, text: str):
    speaker = (speaker or "").strip()
    text = (text or "").strip()
    if not speaker or not text:
        return

    with LOCK:
        if Turn is not None:
            try:
                STATE.turns.append(Turn(speaker=speaker, text=text))
                return
            except Exception:
                pass

        STATE.turns.append({"speaker": speaker, "text": text, "ts": time.time()})


def _run_coach_if_available():
    if generate_coach is None:
        return None
    try:
        coach_obj = generate_coach(STATE, mode="live")
        with LOCK:
            STATE.last_coach = coach_obj
        return coach_obj
    except Exception as e:
        with LOCK:
            STATE.last_coach = {"error": str(e), "_meta": {"ts": time.time()}}
        return STATE.last_coach


def _on_text(speaker: str, text: str):
    _append_turn(speaker, text)
    _run_coach_if_available()


audio_controller = DualAudioController(on_text=_on_text)


@app.get("/", response_class=HTMLResponse)
def root():
    return Path(__file__).with_name("ui.html").read_text(encoding="utf-8")


@app.get("/audio/devices")
def audio_devices():
    return list_audio_devices()


@app.post("/audio/start")
def audio_start(req: AudioStartReq):
    try:
        mic = req.mic_device_index if req.mic_device_index is not None else -1
        vm = req.vm_device_index if req.vm_device_index is not None else -1
        audio_controller.start(mic, vm)
        return {"ok": True, "mic_device_index": mic, "vm_device_index": vm}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/audio/stop")
def audio_stop():
    audio_controller.stop()
    return {"ok": True}


@app.get("/audio/status")
def audio_status():
    return audio_controller.status()


@app.post("/add_line")
def add_line(req: AddLineReq):
    _append_turn(req.speaker, req.text)
    coach_obj = _run_coach_if_available()
    return {"ok": True, "coach": coach_obj}


@app.post("/clear")
def clear():
    with LOCK:
        try:
            STATE.turns = []
        except Exception:
            pass
        try:
            STATE.last_coach = {}
        except Exception:
            pass
    return {"ok": True}


@app.post("/deep_analysis")
def deep_analysis():
    if generate_coach is None:
        return JSONResponse({"ok": False, "error": "coach.py not available"}, status_code=501)
    try:
        coach_obj = generate_coach(STATE, mode="deep")
        with LOCK:
            STATE.last_coach = coach_obj
        return {"ok": True, "coach": coach_obj}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/state")
def get_state():
    with LOCK:
        turns: List[Dict[str, Any]] = []
        for t in getattr(STATE, "turns", []) or []:
            if isinstance(t, dict):
                turns.append(t)
            else:
                turns.append(
                    {
                        "speaker": getattr(t, "speaker", ""),
                        "text": getattr(t, "text", ""),
                        "ts": getattr(t, "ts", None),
                    }
                )

        return {
            "topic": getattr(STATE, "topic", ""),
            "scope": getattr(STATE, "scope", ""),
            "turns": turns,
            "last_coach": getattr(STATE, "last_coach", {}),
        }
