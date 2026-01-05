from fastapi.responses import HTMLResponse
from pathlib import Path
import threading
import time
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from state import STATE, Turn
from coach import generate_coach  # unified entrypoint
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

STATE_LOCK = threading.Lock()

# -----------------------
# API models
# -----------------------

class SetTopicReq(BaseModel):
    topic: str
    scope: str = ""

class AddLineReq(BaseModel):
    speaker: str  # "A" or "B"
    text: str

class AudioStartReq(BaseModel):
    mic_device_index: int
    vm_device_index: int

# -----------------------
# Core logic
# -----------------------

def ingest_line(speaker: str, text: str):
    """
    Single ingestion path for BOTH:
      - typed input (/add_line)
      - Deepgram audio transcripts (mic + voicemeeter)

    IMPORTANT:
      - Never throws on coach errors (prevents audio thread crashes)
      - Live coaching is debounced in coach.generate_coach()
      - Deep analysis is on-demand via /deep_analysis
    """
    speaker = (speaker or "").strip()
    text = (text or "").strip()
    if not speaker or not text:
        return None

    with STATE_LOCK:
        STATE.turns.append(Turn(speaker=speaker, text=text))

    try:
        coach_obj = generate_coach(STATE, mode="live")
        if coach_obj:
            with STATE_LOCK:
                STATE.last_coach = coach_obj
        return {"ok": True, "coach": coach_obj}
    except Exception as e:
        with STATE_LOCK:
            STATE.last_coach = {"error": str(e), "_meta": {"ts": time.time()}}
        return {"ok": False, "error": str(e)}

# Audio controller (calls ingest_line)
audio_controller = DualAudioController(on_text=lambda spk, txt: ingest_line(spk, txt))

# -----------------------
# Routes
# -----------------------

@app.post("/clear")
def clear():
    with STATE_LOCK:
        STATE.turns = []
        STATE.rolling_summary = ""
        STATE.last_coach = {}
    return {"ok": True}

@app.post("/set_topic")
def set_topic(req: SetTopicReq):
    with STATE_LOCK:
        STATE.topic = req.topic
        STATE.scope = req.scope
    return {"ok": True, "topic": req.topic, "scope": req.scope}

@app.get("/state")
def get_state():
    with STATE_LOCK:
        return {
            "topic": getattr(STATE, "topic", ""),
            "scope": getattr(STATE, "scope", ""),
            "turns": [{"speaker": t.speaker, "text": t.text, "ts": t.ts} for t in STATE.turns],
            "rolling_summary": getattr(STATE, "rolling_summary", ""),
            "last_coach": getattr(STATE, "last_coach", {}),

            # ✅ Useful debug info for the UI (so providerInfo actually shows)
            "coach_live_provider": os.getenv("COACH_LIVE_PROVIDER", "ollama"),
            "coach_deep_provider": os.getenv("COACH_DEEP_PROVIDER", "ollama"),
            "coach_debounce_seconds": os.getenv("COACH_DEBOUNCE_SECONDS", "3.0"),
        }

@app.post("/add_line")
def add_line(req: AddLineReq):
    return ingest_line(req.speaker, req.text)

@app.post("/deep_analysis")
def deep_analysis():
    """
    On-demand deeper coaching (provider controlled via env).
    """
    try:
        coach_obj = generate_coach(STATE, mode="deep")
        with STATE_LOCK:
            STATE.last_coach = coach_obj
        return {"ok": True, "coach": coach_obj}
    except Exception as e:
        with STATE_LOCK:
            STATE.last_coach = {"error": str(e), "_meta": {"ts": time.time()}}
        return {"ok": False, "error": str(e)}

# ✅ OPTION B: Serve UI from /ui/index.html (NOT ui.html)
@app.get("/", response_class=HTMLResponse)
def ui():
    return Path(__file__).with_name("ui").joinpath("app.html").read_text(encoding="utf-8")

# -----------------------
# Audio endpoints
# -----------------------

@app.get("/audio/devices")
def audio_devices():
    return {"devices": list_audio_devices()}

@app.post("/audio/start")
def audio_start(req: AudioStartReq):
    try:
        audio_controller.start(req.mic_device_index, req.vm_device_index)
        return {"ok": True, "mic_device_index": req.mic_device_index, "vm_device_index": req.vm_device_index}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/audio/stop")
def audio_stop():
    audio_controller.stop()
    return {"ok": True}

@app.get("/audio/status")
def audio_status():
    return audio_controller.status()
