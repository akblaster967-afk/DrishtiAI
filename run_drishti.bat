@echo off
setlocal
title DrishtiAI Launcher

REM ============================================================
REM  DrishtiAI - One-click launcher (Backend + Frontend)
REM  Starts: FastAPI backend  -> http://127.0.0.1:8000
REM         Vite React app   -> http://localhost:5173
REM ============================================================

cd /d "%~dp0"

echo ==================================================
echo             DrishtiAI - Starting...
echo ==================================================
echo.

REM --- 1. Check Node.js / npm ---
where npm >nul 2>nul
if errorlevel 1 (
    echo [ERROR] npm not found. Please install Node.js from https://nodejs.org
    pause
    exit /b 1
)

REM --- 2. Check Python ---
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] python not found. Please install Python 3 from https://python.org
    pause
    exit /b 1
)

REM --- 3. Install frontend dependencies if missing ---
if not exist "node_modules" (
    echo [SETUP] node_modules missing - installing frontend dependencies...
    call npm install
    if errorlevel 1 (
        echo [ERROR] npm install failed.
        pause
        exit /b 1
    )
)

REM --- 4. Install backend dependencies if missing ---
python -c "import fastapi, uvicorn" >nul 2>nul
if errorlevel 1 (
    echo [SETUP] Backend dependencies missing - installing...
    pip install -r backend\requirements.txt
)

echo.
echo   Backend  : http://127.0.0.1:8000   (API docs at /docs)
echo   Frontend : http://localhost:5173
echo.
echo   Open http://localhost:5173 in your browser.
echo   Press Ctrl+C to stop both servers.
echo.

REM --- 5. Start backend + frontend together ---
call npm run dev

pause
