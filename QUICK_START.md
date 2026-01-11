# Quick Start: Get TCP Connected + Bytes Increasing

## Prerequisites
- Python 3.8+
- CMake 3.10+
- C++ compiler (MSVC or MinGW on Windows)

## Quick Test Script

Run the test script first to verify your setup:

**Windows PowerShell**:
```powershell
.\test_quick.ps1
```

**Linux/Mac**:
```bash
chmod +x test_quick.sh
./test_quick.sh
```

## Steps (5 minutes)

### 1. Install Python Dependencies
```bash
pip install -r requirements.txt
```

### 2. Build Audio Engine
```bash
cd engine
mkdir build
cd build
cmake ..
cmake --build . --config Release
cd ../..
```

**Expected**: `engine/build/audio_engine.exe` exists

### 3. Verify Engine Path
Check `backend/audio_engine.py` line 12:
```python
ENGINE_EXE = "engine/build/audio_engine.exe"
```
If your executable is named differently or in a different location, update this.

### 4. Start Backend
```bash
python -m backend.main
```

**Expected output**:
```
INFO:     Started server process
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 5. Test in Browser
1. Open `http://localhost:8000`
2. Click **"Start Audio"** button
3. Wait 1-2 seconds
4. Check status in browser (should show "Running | Mic: X bytes | Loopback: Y bytes")

### 6. Verify Status Endpoint
```bash
curl http://localhost:8000/audio/status
```

**Expected JSON**:
```json
{
  "engine": {"running": true},
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

Bytes should increase over time (960 bytes/second per stream = 1920 bytes every 2 seconds).

## ✅ Success Criteria

- `/audio/status` returns `engine.running: true`
- `/audio/status` returns `mic.tcp_connected: true`
- `/audio/status` returns `loopback.tcp_connected: true`
- `bytes_received` values increase when you poll the endpoint

## 🐛 Troubleshooting

| Problem | Solution |
|---------|----------|
| "Engine executable not found" | Check `ENGINE_EXE` path in `backend/audio_engine.py` |
| "Connection refused" | Ensure engine built successfully, check ports 17711/17712 |
| Bytes not increasing | Check backend logs, verify TCP sockets connected |
| Import errors | Run `python -m backend.main` from project root |

## Next: Phase 2
Once this works, proceed to hook Deepgram transcription.
