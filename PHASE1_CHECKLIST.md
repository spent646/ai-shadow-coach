# Phase 1: TCP Connection + Status Checklist

## Goal
Achieve `/audio/status` showing:
- `engine.running: true`
- `mic.tcp_connected: true` with increasing `bytes_received`
- `loopback.tcp_connected: true` with increasing `bytes_received`

## Steps to Complete

### 1. Build Audio Engine
```bash
cd engine
mkdir build
cd build
cmake ..
cmake --build . --config Release
```

**Expected output**: `engine/build/audio_engine.exe` (or `audio_engine` on non-Windows)

**Current status**: ✅ CMakeLists.txt and minimal stub `main.cpp` created

### 2. Test Engine Manually (Optional)
Run the engine executable directly:
```bash
engine/build/audio_engine.exe
```

**Expected**: Should print:
```
Audio Engine v1 - TCP Server (Test Stub)
Port 17711 = Microphone
Port 17712 = Loopback
Sending dummy PCM data: 48kHz, mono, int16, 20ms frames

[MIC] Listening on port 17711
[LOOPBACK] Listening on port 17712
```

### 3. Update Backend Engine Path
Edit `backend/audio_engine.py` line 12:
```python
ENGINE_EXE = "engine/build/audio_engine.exe"  # Adjust if needed
```

If your build output is different, update this path.

### 4. Start Backend
```bash
pip install -r requirements.txt
python -m backend.main
```

Or:
```bash
uvicorn backend.main:app --reload
```

**Expected**: Server starts on `http://localhost:8000`

### 5. Test TCP Connection
1. Open browser to `http://localhost:8000`
2. Click "Start Audio" button
3. Check browser console for errors
4. Check backend logs for connection status

### 6. Verify Status Endpoint
```bash
curl http://localhost:8000/audio/status
```

**Expected response**:
```json
{
  "engine": {
    "running": true
  },
  "mic": {
    "tcp_connected": true,
    "bytes_received": <increasing number>
  },
  "loopback": {
    "tcp_connected": true,
    "bytes_received": <increasing number>
  }
}
```

## Troubleshooting

### Engine executable not found
- Check `engine/build/` directory exists
- Verify build completed successfully
- Update `ENGINE_EXE` path in `backend/audio_engine.py`

### Connection refused
- Ensure engine is running (or backend spawns it correctly)
- Check ports 17711 and 17712 are not in use
- Verify firewall isn't blocking localhost connections

### Bytes not increasing
- Check engine is actually sending data
- Verify TCP sockets are connected (check status endpoint)
- Check backend logs for errors in `_read_mic_stream` or `_read_loopback_stream`

### Backend import errors
- Ensure you're running from project root
- Try: `python -m backend.main` instead of `python backend/main.py`
- Check `backend/__init__.py` exists

## Next Phase
Once Phase 1 is complete:
- Phase 2: Hook Deepgram transcription
- Phase 3: UI transcript pane updates
- Phase 4: Ollama coach chat
