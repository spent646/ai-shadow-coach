"""FastAPI backend for AI Shadow Coach v1."""

from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
import time
import asyncio
import json
from queue import Queue
import threading

from backend.models import TranscriptEvent, CoachMessage
from backend.audio_engine import AudioEngine
from backend.transcriber import DeepgramTranscriber
from backend.coach import Coach

app = FastAPI(title="AI Shadow Coach v1")

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state
audio_engine = AudioEngine()
transcriber: Optional[DeepgramTranscriber] = None
coach = Coach()
transcript_queue = Queue()  # Thread-safe queue for transcript events


# Request models
class ChatRequest(BaseModel):
    message: str


# Transcript event callback
def on_transcript_event(stream: str, text: str, is_final: bool):
    """Callback when transcript event occurs."""
    event = TranscriptEvent(
        ts=time.time(),
        stream=stream,
        text=text,
        is_final=is_final
    )
    transcript_queue.put(event)
    print(f"[TRANSCRIPT] Stream {stream}: {text[:50]}{'...' if len(text) > 50 else ''} (final={is_final})")


@app.get("/favicon.ico")
async def favicon():
    """Return empty favicon to prevent 404 errors."""
    return Response(content="", media_type="image/x-icon")


@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    """Serve the main UI page."""
    with open("backend/ui.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.post("/audio/start")
async def audio_start():
    """Start the audio engine."""
    result = audio_engine.start()
    
    # Initialize transcriber if engine started successfully
    if "status" in result and result["status"] == "started":
        global transcriber
        transcriber = DeepgramTranscriber()
        transcriber.start_stream("A", lambda text, final: on_transcript_event("A", text, final))
        transcriber.start_stream("B", lambda text, final: on_transcript_event("B", text, final))
        
        # Connect transcriber to audio engine so it receives audio data
        audio_engine.set_transcriber(transcriber)
    
    return result


@app.post("/audio/stop")
async def audio_stop():
    """Stop the audio engine."""
    global transcriber
    if transcriber:
        transcriber.shutdown()
        transcriber = None
    
    return audio_engine.stop()


@app.get("/audio/status")
async def audio_status():
    """Get audio engine status."""
    return audio_engine.get_status()


@app.get("/transcript/stream")
async def transcript_stream():
    """Stream transcript events via Server-Sent Events."""
    
    async def event_generator():
        while True:
            try:
                # Get event from queue (non-blocking)
                try:
                    event = transcript_queue.get(timeout=1.0)
                    if event:
                        # Format as SSE
                        event_dict = event.to_dict()
                        event_json = json.dumps(event_dict)
                        yield f"data: {event_json}\n\n"
                except:
                    # Send heartbeat to keep connection alive
                    yield ": heartbeat\n\n"
                
                await asyncio.sleep(0.1)
            except Exception as e:
                print(f"Error in transcript stream: {e}")
                import traceback
                traceback.print_exc()
                break
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable buffering for nginx
        }
    )


@app.post("/coach/chat")
async def coach_chat(request: ChatRequest):
    """Send message to coach and get response."""
    # Get recent transcript context (last 20 events)
    recent_events = []
    temp_queue = []
    while not transcript_queue.empty():
        temp_queue.append(transcript_queue.get())
    recent_events = temp_queue[-20:]
    # Put them back
    for event in temp_queue:
        transcript_queue.put(event)
    
    response_text = coach.chat(request.message, recent_events)
    
    return {
        "response": response_text,
        "history": coach.get_history()
    }


@app.get("/coach/history")
async def coach_history():
    """Get coach conversation history."""
    return {"history": coach.get_history()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
