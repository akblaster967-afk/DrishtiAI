@echo off
setlocal
title DrishtiAI - Stop servers

REM ============================================================
REM  DrishtiAI - Stop backend (port 8000) and frontend (port 5173)
REM  WARNING: kills whatever process is listening on those ports.
REM ============================================================

echo.
echo Stopping DrishtiAI servers (ports 8000 and 5173)...
echo.

powershell -NoProfile -Command "$ports = 8000,5173; $conns = Get-NetTCPConnection -LocalPort $ports -State Listen -ErrorAction SilentlyContinue; if (-not $conns) { Write-Host 'No running servers found on ports 8000/5173.' } else { $conns | Select-Object -Unique OwningProcess | ForEach-Object { $p = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue; if ($p) { Write-Host ('Stopping PID ' + $p.Id + ' (' + $p.ProcessName + ')'); Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } } ; Write-Host 'Done.' }"

echo.
pause
