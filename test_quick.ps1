# Quick Test Script for Windows PowerShell
# Run this to quickly test the setup

Write-Host "=== AI Shadow Coach - Quick Test ===" -ForegroundColor Cyan
Write-Host ""

# Check if engine exists
$enginePath = "engine\build\audio_engine.exe"
if (Test-Path $enginePath) {
    Write-Host "[OK] Engine executable found: $enginePath" -ForegroundColor Green
} else {
    Write-Host "[ERROR] Engine not found: $enginePath" -ForegroundColor Red
    Write-Host "  Run: cd engine && mkdir build && cd build && cmake .. && cmake --build . --config Release" -ForegroundColor Yellow
    exit 1
}

# Check Python dependencies
Write-Host ""
Write-Host "Checking Python dependencies..." -ForegroundColor Cyan
try {
    $result = python -c "import fastapi, uvicorn, requests; print('OK')" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] Python dependencies installed" -ForegroundColor Green
    } else {
        Write-Host "[WARN] Some dependencies missing. Run: pip install -r requirements.txt" -ForegroundColor Yellow
    }
} catch {
    Write-Host "[WARN] Could not check dependencies" -ForegroundColor Yellow
}

# Check if backend can start (quick syntax check)
Write-Host ""
Write-Host "Checking backend syntax..." -ForegroundColor Cyan
try {
    $result = python -m py_compile backend\main.py 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] Backend syntax is valid" -ForegroundColor Green
    } else {
        Write-Host "[ERROR] Backend has syntax errors" -ForegroundColor Red
        Write-Host $result
        exit 1
    }
} catch {
    Write-Host "[WARN] Could not check syntax" -ForegroundColor Yellow
}

# Check ports
Write-Host ""
Write-Host "Checking if ports are available..." -ForegroundColor Cyan
$port8000 = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
$port17711 = Get-NetTCPConnection -LocalPort 17711 -ErrorAction SilentlyContinue
$port17712 = Get-NetTCPConnection -LocalPort 17712 -ErrorAction SilentlyContinue

if ($port8000) {
    Write-Host "[WARN] Port 8000 is in use (backend port)" -ForegroundColor Yellow
} else {
    Write-Host "[OK] Port 8000 is available" -ForegroundColor Green
}

if ($port17711) {
    Write-Host "[WARN] Port 17711 is in use (mic TCP port)" -ForegroundColor Yellow
} else {
    Write-Host "[OK] Port 17711 is available" -ForegroundColor Green
}

if ($port17712) {
    Write-Host "[WARN] Port 17712 is in use (loopback TCP port)" -ForegroundColor Yellow
} else {
    Write-Host "[OK] Port 17712 is available" -ForegroundColor Green
}

Write-Host ""
Write-Host "=== Test Complete ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Start backend: python -m backend.main" -ForegroundColor White
Write-Host "2. Open browser: http://localhost:8000" -ForegroundColor White
Write-Host "3. Click 'Start Audio' button" -ForegroundColor White
Write-Host "4. Check status at: http://localhost:8000/audio/status" -ForegroundColor White
