# AI Shadow Coach v1

A minimal v1 desktop app for real-time conversation coaching with Socratic questioning.

## Architecture

- **Backend**: Python FastAPI server
- **Audio Engine**: Native C/C++ process (TCP server on ports 17711, 17712)
- **UI**: Single-page web UI served by backend
- **Transcription**: Deepgram streaming (via Transcriber abstraction)
- **Coach**: Ollama with Socratic prompt

## Setup

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure API Keys (Optional for Phase 1)

For Phase 1 (TCP connection testing), no API keys are needed. When you're ready for Phase 2 (transcription), you'll need a Deepgram API key.

See `API_KEYS.md` for detailed instructions. Quick setup:

```bash
# Copy example file
cp env.example .env

# Edit .env and add your Deepgram API key
# DEEPGRAM_API_KEY=your_key_here
```

### 3. Build Audio Engine

```bash
cd engine
mkdir build
cd build
cmake ..
cmake --build .
```

This should produce `audio_engine.exe` in `engine/build/`.

### 4. Start Backend

```bash
python -m backend.main
```

Or with uvicorn directly:

```bash
uvicorn backend.main:app --reload
```

### 5. Open UI

Navigate to `http://localhost:8000` in your browser.

## Definition of Done

1. ✅ Build engine executable
2. ✅ Run backend server
3. ✅ Open UI in browser
4. ✅ Click "Start Audio" → `/audio/status` shows:
   - `engine.running: true`
   - `mic.tcp_connected: true` with increasing `bytes_received`
   - `loopback.tcp_connected: true` with increasing `bytes_received`
5. ✅ Transcript lines appear in UI (A/B labeled)
6. ✅ Coach chat works with Socratic questions

## API Endpoints

- `POST /audio/start` - Start audio engine
- `POST /audio/stop` - Stop audio engine
- `GET /audio/status` - Get engine status
- `GET /transcript/stream` - SSE stream of transcript events
- `POST /coach/chat` - Send message to coach
- `GET /coach/history` - Get conversation history

## Next Steps (Phase 1)

To achieve "TCP connected + bytes increasing":

1. **Audio Engine**: Implement TCP server in `engine/src/main.cpp`:
   - Listen on ports 17711 (mic) and 17712 (loopback)
   - Accept connections
   - Send PCM frames (48kHz, mono, int16, 20ms = 1920 bytes)

2. **Backend**: TCP client connection is already implemented in `backend/audio_engine.py`

3. **Test**: Start engine manually, then start backend, click "Start Audio", check `/audio/status`

## Minimal Engine Stub

If you need a quick test stub, create `engine/src/main.cpp` with a simple TCP server that sends dummy PCM data. See `engine/README.md` for details.
