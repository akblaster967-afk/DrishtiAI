@echo off
setlocal
title DrishtiAI - Backend only

REM ============================================================
REM  DrishtiAI - Backend only (FastAPI + Uvicorn)
REM  Runs: http://127.0.0.1:8000  (Swagger docs at /docs)
REM  NOTE: Frontend must be running separately (run_frontend.bat)
REM        or via run_drishti.bat to use the web UI.
REM ============================================================

cd /d "%~dp0"

echo ==============================================
echo        DrishtiAI Backend - Starting...
echo ==============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] python not found. Please install Python 3 from https://python.org
    pause
    exit /b 1
)

python -c "import fastapi, uvicorn" >nul 2>nul
if errorlevel 1 (
    echo [SETUP] Backend dependencies missing - installing...
    pip install -r backend\requirements.txt
)

echo.
echo   Backend API : http://127.0.0.1:8000
echo   API docs    : http://127.0.0.1:8000/docs
echo   Press Ctrl+C to stop.
echo.

python -m uvicorn app.main:app --app-dir backend --reload --port 8000

pause
