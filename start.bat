@echo off
setlocal enabledelayedexpansion
title Lexa AI Launcher
color 0F
cd /d "%~dp0"

echo.
echo  ========================================
echo       LEXA AI v1.0.0 - Starting...
echo  ========================================
echo.

set "ERRORS=0"
set "WARNINGS=0"

:: Personal OS may live next to the synced Desktop while Lexa lives in this repo.
if not defined PERSONAL_OS_ROOT (
    if exist "%USERPROFILE%\OneDrive - Office\Desktop\OS\11_Integrations\MCP\os-mcp-server\dist\index.js" (
        set "PERSONAL_OS_ROOT=%USERPROFILE%\OneDrive - Office\Desktop\OS"
    ) else if exist "%USERPROFILE%\OneDrive\Desktop\OS\11_Integrations\MCP\os-mcp-server\dist\index.js" (
        set "PERSONAL_OS_ROOT=%USERPROFILE%\OneDrive\Desktop\OS"
    ) else if exist "%USERPROFILE%\Desktop\OS\11_Integrations\MCP\os-mcp-server\dist\index.js" (
        set "PERSONAL_OS_ROOT=%USERPROFILE%\Desktop\OS"
    )
)
if not defined PERSONAL_OS_SDK_ROOT (
    if defined PERSONAL_OS_ROOT set "PERSONAL_OS_SDK_ROOT=%PERSONAL_OS_ROOT%"
)

:: ========================================
::  0. Free old Lexa backend port
:: ========================================
echo  [0/6] Checking old Lexa backend port...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING" 2^>nul') do (
    taskkill /f /pid %%a >nul 2>&1
)
call :STOP_LEXA_ELECTRON
timeout /t 1 /nobreak >nul 2>&1
call :OK "Backend port cleanup complete"

:: ========================================
::  1. Check Python installation
:: ========================================
echo  [1/6] Checking Python...
where python >nul 2>&1
if errorlevel 1 (
    call :ERROR "Python not found in PATH! Install Python 3.11+ first."
    goto :fatal
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do set "PY_VER=%%v"
call :OK "Found %PY_VER%"

:: ========================================
::  2. Check / create Python venv
:: ========================================
echo  [2/6] Checking Python venv...
if not exist "venv\Scripts\python.exe" (
    call :WARN "venv not found - creating virtual environment..."
    python -m venv venv
    if errorlevel 1 (
        call :ERROR "Failed to create venv!"
        goto :fatal
    )
    call :OK "venv created successfully"
) else (
    call :OK "venv exists"
)

venv\Scripts\python.exe -m pip show fastapi >nul 2>&1
if errorlevel 1 (
    call :WARN "Dependencies missing - installing from requirements.txt..."
    venv\Scripts\python.exe -m pip install -r requirements.txt --quiet
    if errorlevel 1 (
        call :ERROR "pip install failed! Check requirements.txt."
        goto :fatal
    )
    call :OK "Dependencies installed"
) else (
    call :OK "Dependencies OK (fastapi found)"
)

:: ========================================
::  3. Check Node.js and npm
:: ========================================
echo  [3/6] Checking Node.js...
where node >nul 2>&1
if errorlevel 1 (
    call :ERROR "Node.js not found in PATH! Install Node.js 18+ first."
    goto :fatal
)
for /f "tokens=*" %%v in ('node --version 2^>^&1') do set "NODE_VER=%%v"
call :OK "Found Node.js %NODE_VER%"

where npm >nul 2>&1
if errorlevel 1 (
    call :ERROR "npm not found in PATH!"
    goto :fatal
)

:: ========================================
::  4. Check frontend node_modules
:: ========================================
echo  [4/6] Checking frontend dependencies...
if not exist "frontend\node_modules" (
    call :WARN "node_modules not found - running npm install..."
    cd frontend
    call npm install
    if errorlevel 1 (
        call :ERROR "npm install failed!"
        cd /d "%~dp0"
        goto :fatal
    )
    cd /d "%~dp0"
    call :OK "Frontend dependencies installed"
) else (
    call :OK "Frontend node_modules exists"
)

:: ========================================
::  5. Check API keys (keyring)
:: ========================================
echo  [5/6] Checking cloud API keys...

venv\Scripts\python.exe -c "import keyring; exit(0 if keyring.get_password('lexa-ai','groq_api_key') else 1)" >nul 2>&1
if errorlevel 1 (
    call :WARN "Groq API key not found - cloud chat may use other providers or Ollama."
    set /a WARNINGS+=1
) else (
    call :OK "Groq API key found"
)

venv\Scripts\python.exe -c "import keyring; exit(0 if keyring.get_password('lexa-ai','openai_api_key') else 1)" >nul 2>&1
if errorlevel 1 (
    call :WARN "OpenAI API key not found - optional provider unavailable."
    set /a WARNINGS+=1
) else (
    call :OK "OpenAI API key found"
)

venv\Scripts\python.exe -c "import keyring; exit(0 if keyring.get_password('lexa-ai','deepgram_api_key') else 1)" >nul 2>&1
if errorlevel 1 (
    call :WARN "Deepgram API key not found - STT will fall back to Groq or local."
    set /a WARNINGS+=1
) else (
    call :OK "Deepgram Nova-3 STT key found"
)

venv\Scripts\python.exe -c "import keyring; exit(0 if keyring.get_password('lexa-ai','cartesia_api_key') else 1)" >nul 2>&1
if errorlevel 1 (
    call :WARN "Cartesia API key not found - TTS may use ElevenLabs or SAPI."
    set /a WARNINGS+=1
) else (
    call :OK "Cartesia Sonic TTS key found"
)

venv\Scripts\python.exe -c "import keyring; exit(0 if keyring.get_password('lexa-ai','elevenlabs_api_key') else 1)" >nul 2>&1
if errorlevel 1 (
    call :WARN "ElevenLabs API key not found - premium voices unavailable."
    set /a WARNINGS+=1
) else (
    call :OK "ElevenLabs TTS key found"
)

:: ========================================
::  6. Double-check port 8000
:: ========================================
echo  [6/6] Checking port 8000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING" 2^>nul') do (
    call :WARN "Port 8000 still in use (PID %%a) - killing..."
    taskkill /f /pid %%a >nul 2>&1
    timeout /t 1 /nobreak >nul 2>&1
)
call :OK "Port 8000 is free"

:: ========================================
::  Start Electron (backend is managed by main.js)
:: ========================================
echo.
echo  Starting Lexa AI (Electron + Backend)...
set "ELECTRON_RUN_AS_NODE="
pushd "%~dp0frontend"
start "Lexa AI" npx electron .
popd

:: ========================================
::  Summary
:: ========================================
echo.
echo  ========================================
if !WARNINGS! gtr 0 (
    echo   Lexa AI started with !WARNINGS! warning(s)
) else (
    echo   Lexa AI is running!
)
echo  ========================================
echo   App:      Electron + FastAPI (auto-managed)
echo   Commands: 138+ registered
echo   Views:    7 (Dashboard, Chat, System,
echo             Commands, Productivity, Memory,
echo             Settings)
echo   AI:       Groq + OpenAI + Gemini + Ollama
echo   STT:      Deepgram Nova-3 + Groq/Local fallback
echo   TTS:      Cartesia + ElevenLabs + SAPI fallback
echo  ========================================
echo.
echo  Press any key to stop Lexa AI...
pause >nul

:: ========================================
::  Cleanup on exit
:: ========================================
echo.
echo  Stopping Lexa AI...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING" 2^>nul') do (
    taskkill /f /pid %%a >nul 2>&1
)
call :STOP_LEXA_ELECTRON
echo  Done. Goodbye!
exit /b 0

:: ========================================
::  Helper functions
:: ========================================

:STOP_LEXA_ELECTRON
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p = Join-Path '%~dp0' 'frontend\node_modules\electron\dist\electron.exe'; if (Test-Path -LiteralPath $p) { $resolved = (Resolve-Path -LiteralPath $p).Path; Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'electron.exe' -and $_.ExecutablePath -eq $resolved } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } }" >nul 2>&1
exit /b 0

:OK
echo    [OK]   %~1
exit /b 0

:WARN
echo    [WARN] %~1
exit /b 0

:ERROR
echo    [FAIL] %~1
set /a ERRORS+=1
exit /b 0

:fatal
echo.
echo  ========================================
echo   FATAL: Lexa AI could not start.
echo   Fix the errors above and try again.
echo  ========================================
echo.
echo  Press any key to exit...
pause >nul
exit /b 1
