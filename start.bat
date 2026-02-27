@echo off
title Lexa AI Launcher
color 0A
echo.
echo  ========================================
echo       LEXA AI v0.5.0 — Starting...
echo  ========================================
echo.

:: Check Python
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
    echo  [ERROR] Python venv not found!
    echo  Run: python -m venv venv
    echo  Then: venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

:: Check Node
cd frontend
if not exist "node_modules" (
    echo  [WARN] node_modules not found, installing...
    call npm install
)
cd /d "%~dp0"

:: Kill old instances
taskkill /f /im python.exe >nul 2>&1

:: Start Backend
echo  [1/2] Starting Backend (FastAPI on port 8000)...
start /min "Lexa Backend" cmd /c "venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload"

:: Wait for backend to be ready
echo  Waiting for backend...
timeout /t 4 /nobreak >nul

:: Verify backend is running
curl -s http://127.0.0.1:8000/health >nul 2>&1
if errorlevel 1 (
    echo  [WARN] Backend may still be loading...
    timeout /t 3 /nobreak >nul
)

:: Start Frontend
echo  [2/2] Starting Frontend (Electron)...
cd frontend
start "Lexa Frontend" cmd /c "npx electron ."
cd /d "%~dp0"

echo.
echo  ========================================
echo   Lexa AI is running!
echo   Backend:  http://127.0.0.1:8000
echo   Commands: 60 registered
echo   AI:       Groq + Ollama Fallback
echo   Voice:    Piper TTS + Whisper STT
echo  ========================================
echo.
echo  Press any key to stop Lexa AI...
pause >nul

:: Cleanup
echo  Stopping Lexa AI...
taskkill /f /im python.exe >nul 2>&1
taskkill /f /im electron.exe >nul 2>&1
echo  Done.
