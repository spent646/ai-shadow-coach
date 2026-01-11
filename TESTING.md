# Testing Guide

## Quick Test (5 minutes)

### Step 1: Build the Audio Engine

```bash
cd engine
mkdir build
cd build
cmake ..
cmake --build . --config Release
cd ../..
```

**Expected**: `engine/build/audio_engine.exe` should exist

**Troubleshooting**:
- If CMake not found: Install CMake from https://cmake.org/
- If build fails: Check you have a C++ compiler (Visual Studio on Windows, or MinGW)

### Step 2: Install Python Dependencies

```bash
pip install -r requirements.txt
```

**Expected**: All packages install successfully

### Step 3: Start the Backend

```bash
python -m backend.main
```

**Expected output**:
```
INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

**Troubleshooting**:
- Port 8000 in use? Change port: `uvicorn backend.main:app --port 8001`
- Import errors? Make sure you're in the project root directory

### Step 4: Test in Browser

1. Open `http://localhost:8000` in your browser
2. You should see the UI with two panes:
   - Left: "Live Transcript" pane
   - Right: "Coach Chat" pane
3. At the top, you should see:
   - "Start Audio" button
   - "Stop Audio" button (disabled)
   - Status showing "Stopped"

### Step 5: Test Audio Engine Connection

1. Click the **"Start Audio"** button
2. Wait 1-2 seconds
3. Check the status display - it should show:
   - "Running | Mic: X bytes | Loopback: Y bytes"
   - The byte counts should increase over time

**Expected behavior**:
- Backend spawns `engine/build/audio_engine.exe`
- Engine starts TCP servers on ports 17711 and 17712
- Backend connects to both ports
- Bytes received counter increases

### Step 6: Verify Status Endpoint

Open a new terminal and test the API:

```bash
# Windows PowerShell
curl http://localhost:8000/audio/status

# Or use a browser
# Navigate to: http://localhost:8000/audio/status
```

**Expected JSON response**:
```json
{
  "engine": {
    "running": true
  },
  "mic": {
    "tcp_connected": true,
    "bytes_received": 19200
  },
  "loopback": {
    "tcp_connected": true,
    "bytes_received": 19200
  }
}
```

**Success criteria**:
- ✅ `engine.running: true`
- ✅ `mic.tcp_connected: true`
- ✅ `loopback.tcp_connected: true`
- ✅ `bytes_received` values increase when you poll again

### Step 7: Test Stop Functionality

1. Click the **"Stop Audio"** button
2. Status should change back to "Stopped"
3. Poll `/audio/status` again - should show:
   ```json
   {
     "engine": {"running": false},
     "mic": {"tcp_connected": false, "bytes_received": 0},
     "loopback": {"tcp_connected": false, "bytes_received": 0}
   }
   ```

## Manual Testing Checklist

### ✅ Phase 1: TCP Connection

- [ ] Engine builds successfully
- [ ] Backend starts without errors
- [ ] UI loads in browser
- [ ] "Start Audio" button works
- [ ] Status shows `engine.running: true`
- [ ] Status shows `mic.tcp_connected: true`
- [ ] Status shows `loopback.tcp_connected: true`
- [ ] Byte counts increase over time
- [ ] "Stop Audio" button works
- [ ] Status resets after stop

### 🔄 Phase 2: Transcript Streaming (Not Yet Implemented)

- [ ] Transcript events appear in UI
- [ ] Stream A (mic) shows with green label
- [ ] Stream B (loopback) shows with blue label
- [ ] Timestamps are correct
- [ ] Final vs interim transcripts display correctly

### 💬 Phase 3: Coach Chat (Requires Ollama)

- [ ] Ollama is running locally
- [ ] Can send messages to coach
- [ ] Coach responds with Socratic questions
- [ ] Conversation history persists

## Testing with curl (Command Line)

### Test Status Endpoint
```bash
curl http://localhost:8000/audio/status
```

### Start Audio
```bash
curl -X POST http://localhost:8000/audio/start
```

### Stop Audio
```bash
curl -X POST http://localhost:8000/audio/stop
```

### Test Coach Chat (requires Ollama running)
```bash
curl -X POST http://localhost:8000/coach/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"What should I ask about this conversation?\"}"
```

## Common Issues & Solutions

### Issue: "Engine executable not found"
**Solution**: 
- Check `engine/build/audio_engine.exe` exists
- Verify path in `backend/audio_engine.py` line 12
- Rebuild the engine

### Issue: "Connection refused"
**Solution**:
- Check if ports 17711/17712 are in use: `netstat -an | findstr "17711"`
- Kill any process using those ports
- Ensure engine starts before backend tries to connect

### Issue: Bytes not increasing
**Solution**:
- Check backend logs for errors
- Verify engine is actually sending data (check engine console output)
- Test TCP connection manually with `telnet localhost 17711`

### Issue: UI doesn't load
**Solution**:
- Check backend is running on port 8000
- Check browser console for errors (F12)
- Verify `backend/ui.html` exists

### Issue: Import errors
**Solution**:
- Run from project root: `python -m backend.main`
- Don't run from `backend/` directory
- Ensure `backend/__init__.py` exists

## Automated Testing (Future)

For now, testing is manual. Future improvements could include:
- Unit tests for data models
- Integration tests for TCP connection
- End-to-end tests with mock engine

## Next Steps After Testing

Once Phase 1 (TCP connection) works:
1. ✅ Phase 1 complete - TCP connected + bytes increasing
2. → Phase 2: Implement Deepgram transcription
3. → Phase 3: Test transcript streaming in UI
4. → Phase 4: Test Ollama coach chat
