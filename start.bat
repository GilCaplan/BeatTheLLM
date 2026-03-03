@echo off
REM ============================================================
REM Jailbreak the AI — Start Script (Windows)
REM ============================================================
setlocal EnableDelayedExpansion

set ROOT=%~dp0
set BACKEND=%ROOT%backend
set FRONTEND=%ROOT%frontend
set VENV=%ROOT%.venv

echo [JAILBREAK] Setting up Python virtual environment...
if not exist "%VENV%" (
    python -m venv "%VENV%"
    if errorlevel 1 (
        echo [ERROR] Failed to create venv. Is Python installed?
        pause & exit /b 1
    )
)

echo [JAILBREAK] Installing Python dependencies...
"%VENV%\Scripts\pip" install --upgrade pip --quiet
"%VENV%\Scripts\pip" install -r "%BACKEND%\requirements.txt" --quiet

echo [JAILBREAK] Installing Node.js dependencies...
where node >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found. Please install from https://nodejs.org
    pause & exit /b 1
)

pushd "%FRONTEND%"
if not exist "node_modules" (
    npm install --legacy-peer-deps
)
popd

REM Create .env if missing
if not exist "%BACKEND%\.env" (
    echo [JAILBREAK] Creating default .env...
    (
        echo MOCK_LLM=0
        echo LLM_MODEL=TinyLlama/TinyLlama-1.1B-Chat-v1.0
    ) > "%BACKEND%\.env"
)

echo [JAILBREAK] Running backend tests...
set MOCK_LLM=1
"%VENV%\Scripts\pytest" "%BACKEND%\test_game.py" -v --tb=short
if errorlevel 1 (
    echo [ERROR] Tests failed. Fix errors before starting.
    pause & exit /b 1
)
set MOCK_LLM=0
echo [JAILBREAK] All tests passed!

echo.
echo   Backend  ^> http://localhost:8000
echo   Frontend ^> http://localhost:5173
echo.
echo   Close both windows to stop the servers.
echo.

REM Start backend in a new window
start "Jailbreak Backend" cmd /k "set MOCK_LLM=0 && cd /d %BACKEND% && %VENV%\Scripts\python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"

REM Short delay then start frontend
timeout /t 2 >nul
start "Jailbreak Frontend" cmd /k "cd /d %FRONTEND% && npm run dev"

echo [JAILBREAK] Both servers launched in separate windows.
pause
