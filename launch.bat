@echo off
REM AI Shadow Coach - Launch Script (Windows Batch)
REM This script will start the backend server and open the browser

echo AI Shadow Coach - Starting...
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python not found. Please install Python 3.8+ and try again.
    pause
    exit /b 1
)

REM Check if dependencies are installed
echo Checking dependencies...
python -c "import fastapi, uvicorn" >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    pip install -r requirements.txt
)

REM Check if engine executable exists
if not exist "engine\build\Release\audio_engine.exe" (
    echo Warning: Audio engine not found at engine\build\Release\audio_engine.exe
    echo The engine needs to be built first.
    echo.
    echo Continuing anyway (audio features will not work)...
    echo.
)

REM Start the server
echo.
echo Starting backend server...
echo Server will be available at: http://localhost:8000
echo Press Ctrl+C to stop the server
echo.

REM Open browser after a short delay
timeout /t 2 /nobreak >nul
start http://localhost:8000

REM Start the server
python -m backend.main
