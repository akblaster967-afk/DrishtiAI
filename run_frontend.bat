@echo off
setlocal
title DrishtiAI - Frontend only

REM ============================================================
REM  DrishtiAI - Frontend only (Vite dev server)
REM  Runs: http://localhost:5173
REM  NOTE: Backend must be running separately (run_backend.bat)
REM        or via run_drishti.bat, otherwise /api calls will fail.
REM ============================================================

cd /d "%~dp0"

echo ==============================================
echo        DrishtiAI Frontend - Starting...
echo ==============================================
echo.

where npm >nul 2>nul
if errorlevel 1 (
    echo [ERROR] npm not found. Please install Node.js from https://nodejs.org
    pause
    exit /b 1
)

if not exist "node_modules" (
    echo [SETUP] node_modules missing - installing frontend dependencies...
    call npm install
    if errorlevel 1 (
        echo [ERROR] npm install failed.
        pause
        exit /b 1
    )
)

echo.
echo   Frontend : http://localhost:5173
echo   Press Ctrl+C to stop.
echo.

call npx vite

pause
