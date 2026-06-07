@echo off
REM ============================================================================
REM dashboard.bat — manage the FarmOps dashboard server (python app.py)
REM
REM Usage:  dashboard [start|stop|restart|status|urls]
REM
REM Runs from anywhere via the %~dp0 trick (always cd's to its own directory),
REM so you can put a shortcut on the desktop and it still finds app.py.
REM
REM What this DOESN'T start:
REM   - The Laixi app (ws://127.0.0.1:22221/) — that's launched by the Laixi
REM     desktop app itself; make sure it's running before triggering automations.
REM ============================================================================
setlocal
cd /d "%~dp0"

set "ACTION=%~1"
if "%ACTION%"=="" set "ACTION=start"

if /i "%ACTION%"=="start"   goto :do_start
if /i "%ACTION%"=="stop"    goto :do_stop
if /i "%ACTION%"=="restart" goto :do_restart
if /i "%ACTION%"=="status"  goto :do_status
if /i "%ACTION%"=="urls"    goto :urls
goto :usage

:do_start
call :kill_existing
echo.
echo Starting FarmOps dashboard...
REM Launch in a new console window so you can see live logs and Ctrl+C to stop.
start "FarmOps Dashboard - py app.py" cmd /k "set PYTHONIOENCODING=utf-8 && py app.py"
REM Wait a beat, then health-check by hitting index.html.
powershell -NoProfile -Command "Start-Sleep -Milliseconds 1500; try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/index.html' -TimeoutSec 4; Write-Host ('Server responding (HTTP ' + $r.StatusCode + ')') -ForegroundColor Green } catch { Write-Host 'Server did not respond on port 8000 yet - check the new console window for errors.' -ForegroundColor Red }"
call :urls
exit /b 0

:do_stop
call :kill_existing
exit /b 0

:do_restart
call :kill_existing
timeout /t 1 /nobreak >nul
goto :do_start

:do_status
powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*app.py*' }; if ($p) { $p | ForEach-Object { Write-Host ('RUNNING - PID ' + $_.ProcessId) -ForegroundColor Green } } else { Write-Host 'STOPPED' -ForegroundColor DarkGray }"
exit /b 0

:urls
echo.
echo   Dashboard:    http://127.0.0.1:8000/index.html
echo   Proxy times:  http://127.0.0.1:8000/proxy-times.html
echo   Device times: http://127.0.0.1:8000/device-times.html
echo.
exit /b 0

:kill_existing
powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*app.py*' }; if ($p) { $p | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host ('Stopped PID ' + $_.ProcessId) -ForegroundColor Yellow } } else { Write-Host 'No app.py server process found' -ForegroundColor DarkGray }"
exit /b 0

:usage
echo.
echo Usage: dashboard {start^|stop^|restart^|status^|urls}
echo.
echo   start    (default) Stop any existing instance, then launch the server
echo   stop     Stop the running server
echo   restart  Stop then start
echo   status   Show whether the server is running
echo   urls     Print the local dashboard URLs
echo.
exit /b 1
