# AI Shadow Coach - Launch Script
# This script will start the backend server and open the browser

Write-Host "AI Shadow Coach - Starting..." -ForegroundColor Cyan

# Check if Python is available
try {
    $pythonVersion = python --version 2>&1
    Write-Host "Found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "Error: Python not found. Please install Python 3.8+ and try again." -ForegroundColor Red
    exit 1
}

# Check if dependencies are installed
Write-Host "Checking dependencies..." -ForegroundColor Yellow
try {
    python -c "import fastapi, uvicorn" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Installing dependencies..." -ForegroundColor Yellow
        pip install -r requirements.txt
    }
} catch {
    Write-Host "Installing dependencies..." -ForegroundColor Yellow
    pip install -r requirements.txt
}

# Check if engine executable exists
$enginePath = "engine\build\Release\audio_engine.exe"
if (-not (Test-Path $enginePath)) {
    Write-Host "Warning: Audio engine not found at $enginePath" -ForegroundColor Yellow
    Write-Host "The engine needs to be built first. Run:" -ForegroundColor Yellow
    Write-Host "  cd engine" -ForegroundColor Yellow
    Write-Host "  mkdir build" -ForegroundColor Yellow
    Write-Host "  cd build" -ForegroundColor Yellow
    Write-Host "  cmake .." -ForegroundColor Yellow
    Write-Host "  cmake --build . --config Release" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Continuing anyway (audio features will not work)..." -ForegroundColor Yellow
}

# Start the server
Write-Host ""
Write-Host "Starting backend server..." -ForegroundColor Cyan
Write-Host "Server will be available at: http://localhost:8000" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow
Write-Host ""

# Open browser after a short delay
Start-Sleep -Seconds 2
Start-Process "http://localhost:8000"

# Start the server
python -m backend.main
