#!/bin/bash
# Quick Test Script for Linux/Mac
# Run this to quickly test the setup

echo "=== AI Shadow Coach - Quick Test ==="
echo ""

# Check if engine exists
ENGINE_PATH="engine/build/audio_engine"
if [ -f "$ENGINE_PATH" ] || [ -f "${ENGINE_PATH}.exe" ]; then
    echo "[OK] Engine executable found"
else
    echo "[ERROR] Engine not found: $ENGINE_PATH"
    echo "  Run: cd engine && mkdir build && cd build && cmake .. && cmake --build ."
    exit 1
fi

# Check Python dependencies
echo ""
echo "Checking Python dependencies..."
if python3 -c "import fastapi, uvicorn, requests" 2>/dev/null; then
    echo "[OK] Python dependencies installed"
else
    echo "[WARN] Some dependencies missing. Run: pip install -r requirements.txt"
fi

# Check if backend can start (quick syntax check)
echo ""
echo "Checking backend syntax..."
if python3 -m py_compile backend/main.py 2>/dev/null; then
    echo "[OK] Backend syntax is valid"
else
    echo "[ERROR] Backend has syntax errors"
    exit 1
fi

# Check ports (Linux/Mac)
echo ""
echo "Checking if ports are available..."
if command -v lsof &> /dev/null; then
    if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo "[WARN] Port 8000 is in use (backend port)"
    else
        echo "[OK] Port 8000 is available"
    fi
    
    if lsof -Pi :17711 -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo "[WARN] Port 17711 is in use (mic TCP port)"
    else
        echo "[OK] Port 17711 is available"
    fi
    
    if lsof -Pi :17712 -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo "[WARN] Port 17712 is in use (loopback TCP port)"
    else
        echo "[OK] Port 17712 is available"
    fi
else
    echo "[INFO] lsof not available, skipping port check"
fi

echo ""
echo "=== Test Complete ==="
echo ""
echo "Next steps:"
echo "1. Start backend: python3 -m backend.main"
echo "2. Open browser: http://localhost:8000"
echo "3. Click 'Start Audio' button"
echo "4. Check status at: http://localhost:8000/audio/status"
