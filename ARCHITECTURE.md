# AI Shadow Coach v1 - Architecture Plan

## Folder Structure

```
.
├── backend/
│   ├── main.py                 # FastAPI app entry point
│   ├── models.py               # Data models (TranscriptEvent, CoachMessage)
│   ├── audio_engine.py         # TCP client + engine lifecycle management
│   ├── transcriber.py          # Transcriber abstraction (Deepgram implementation)
│   ├── coach.py                # Ollama coach with Socratic prompt
│   └── ui.html                 # Single-page web UI
├── engine/                     # Native audio engine (C/C++ CMake project)
│   ├── CMakeLists.txt
│   ├── src/
│   │   ├── main.cpp            # TCP server (ports 17711, 17712)
│   │   ├── audio_capture.cpp   # WASAPI mic + loopback capture
│   │   └── proof_mode.cpp      # WAV file writing (10s)
│   └── build/                  # Build output
├── requirements.txt            # Python dependencies
└── README.md                   # Setup and run instructions
```

## Data Models

### TranscriptEvent
```python
{
    "ts": float,           # Unix timestamp
    "stream": str,         # "A" (mic) or "B" (loopback)
    "text": str,           # Transcript text
    "is_final": bool       # True for final, False for interim
}
```

### CoachMessage
```python
{
    "role": str,           # "user" or "assistant"
    "text": str,           # Message content
    "ts": float            # Unix timestamp
}
```

## API Endpoints

### Audio Engine Lifecycle
- `POST /audio/start` - Spawns engine process, connects TCP clients
- `POST /audio/stop` - Stops engine, disconnects TCP
- `GET /audio/status` - Returns engine state + TCP connection status + bytes received

### Transcript
- `GET /transcript/stream` - Server-Sent Events (SSE) stream of TranscriptEvent updates

### Coach
- `POST /coach/chat` - Sends user message + conversation context to Ollama, returns assistant reply

## Audio Engine Contract

### TCP Server
- Port 17711: Microphone stream
- Port 17712: System audio (loopback) stream

### PCM Format
- Sample rate: 48000 Hz
- Channels: 1 (mono)
- Bit depth: 16-bit signed integer
- Frame size: 960 samples (20ms) = 1920 bytes per frame

### Proof Mode
- Writes `mic.wav` and `loop.wav` for 10 seconds when enabled

## Implementation Phases

### Phase 1: TCP Connection + Status
- Backend TCP client connects to engine
- `/audio/status` shows `engine.running=true`, `mic.tcp_connected=true`, `loopback.tcp_connected=true` with increasing bytes

### Phase 2: Deepgram Integration
- Hook Deepgram streaming behind Transcriber abstraction
- Push transcript events to SSE stream

### Phase 3: UI Transcript Pane
- Connect UI to `/transcript/stream` SSE
- Display A/B labeled transcript lines with timestamps

### Phase 4: Ollama Coach
- Implement `/coach/chat` endpoint
- Socratic prompt that returns 3-7 questions by default
- Chat UI pane
