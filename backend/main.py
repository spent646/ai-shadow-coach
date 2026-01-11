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
import hashlib
from queue import Queue
import threading

from backend.models import TranscriptEvent, CoachMessage
from backend.audio_engine import AudioEngine
from backend.transcriber import DeepgramTranscriber
from backend.coaches import create_coach
from backend.config import Config

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

# Initialize coach based on configuration
try:
    coach = create_coach(Config.COACH_TYPE)
    print(f"Coach initialized: {Config.COACH_TYPE}")
except ValueError as e:
    print(f"ERROR: {e}")
    print(f"Falling back to Gemini coach...")
    coach = create_coach("gemini")
except Exception as e:
    print(f"ERROR initializing coach: {e}")
    print("Please check your configuration and API keys.")
    coach = None

transcript_queue = Queue()  # Thread-safe queue for transcript events
reflection_queue = Queue()  # Thread-safe queue for auto-reflection messages
reflection_task: Optional[asyncio.Task] = None  # Background task reference
last_reflection_hash: str = ""  # Track transcript changes


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


# Helper functions for reflection system
def get_recent_transcript(seconds: int) -> List[TranscriptEvent]:
    """Get transcript events from the last N seconds.
    
    Args:
        seconds: Time window in seconds
        
    Returns:
        List of transcript events within the time window
    """
    current_time = time.time()
    cutoff_time = current_time - seconds
    
    # Get all events from queue
    temp_queue = []
    while not transcript_queue.empty():
        temp_queue.append(transcript_queue.get())
    
    # Filter by time and put back
    recent = [e for e in temp_queue if e.ts >= cutoff_time]
    for event in temp_queue:
        transcript_queue.put(event)
    
    return recent


def hash_transcript(events: List[TranscriptEvent]) -> str:
    """Hash transcript content for change detection.
    
    Args:
        events: List of transcript events
        
    Returns:
        MD5 hash of final transcript texts
    """
    final_texts = [e.text for e in events if e.is_final]
    if not final_texts:
        return ""
    return hashlib.md5(''.join(final_texts).encode()).hexdigest()


async def periodic_reflection_task():
    """Background task that generates periodic reflection questions."""
    global last_reflection_hash
    
    while True:
        try:
            await asyncio.sleep(Config.COACH_INTERRUPT_INTERVAL_SECONDS)
            
            # Skip if interval is 0 (disabled)
            if Config.COACH_INTERRUPT_INTERVAL_SECONDS == 0:
                continue
            
            # Skip if coach is not initialized
            if coach is None:
                continue
            
            # Get transcript from last N minutes
            transcript_events = get_recent_transcript(Config.COACH_CONTEXT_WINDOW_MINUTES * 60)
            
            # Skip if empty or unchanged
            content_hash = hash_transcript(transcript_events)
            if not transcript_events or content_hash == last_reflection_hash or content_hash == "":
                continue
            
            # Generate reflection
            print(f"[REFLECTION] Generating reflection based on {len(transcript_events)} events...")
            reflection = coach.generate_reflection(transcript_events)
            
            # Push to queue with metadata
            reflection_queue.put({
                "type": "auto_reflection",
                "text": reflection,
                "ts": time.time()
            })
            
            last_reflection_hash = content_hash
            print(f"[REFLECTION] Question generated: {reflection[:80]}{'...' if len(reflection) > 80 else ''}")
            
        except asyncio.CancelledError:
            print("[REFLECTION] Background task cancelled")
            break
        except Exception as e:
            print(f"[REFLECTION] Error in background task: {e}")
            import traceback
            traceback.print_exc()
            # Continue running despite errors
            continue


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
    global transcriber, reflection_task, last_reflection_hash
    
    result = audio_engine.start()
    
    # Initialize transcriber if engine started successfully
    if "status" in result and result["status"] == "started":
        transcriber = DeepgramTranscriber()
        transcriber.start_stream("A", lambda text, final: on_transcript_event("A", text, final))
        transcriber.start_stream("B", lambda text, final: on_transcript_event("B", text, final))
        
        # Connect transcriber to audio engine so it receives audio data
        audio_engine.set_transcriber(transcriber)
        
        # Start background reflection task
        last_reflection_hash = ""  # Reset hash
        reflection_task = asyncio.create_task(periodic_reflection_task())
        print("[REFLECTION] Background task started")
    
    return result


@app.post("/audio/stop")
async def audio_stop():
    """Stop the audio engine."""
    global transcriber, reflection_task
    
    # Stop background reflection task
    if reflection_task:
        reflection_task.cancel()
        try:
            await reflection_task
        except asyncio.CancelledError:
            pass
        reflection_task = None
        print("[REFLECTION] Background task stopped")
    
    # Clear reflection queue
    while not reflection_queue.empty():
        reflection_queue.get()
    
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


@app.get("/coach/reflections/stream")
async def reflection_stream():
    """Stream auto-reflection questions via Server-Sent Events."""
    
    async def event_generator():
        while True:
            try:
                # Get reflection from queue (non-blocking)
                try:
                    reflection = reflection_queue.get(timeout=1.0)
                    if reflection:
                        # Format as SSE
                        reflection_json = json.dumps(reflection)
                        yield f"data: {reflection_json}\n\n"
                except:
                    # Send heartbeat to keep connection alive
                    yield ": heartbeat\n\n"
                
                await asyncio.sleep(0.1)
            except Exception as e:
                print(f"Error in reflection stream: {e}")
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
    if coach is None:
        return {
            "response": "Error: Coach not initialized. Please check your configuration.",
            "history": []
        }
    
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
    if coach is None:
        return {"history": []}
    return {"history": coach.get_history()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
