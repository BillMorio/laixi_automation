@echo off
REM ============================================================================
REM setup.bat — one-time setup for the FarmOps dashboard.
REM
REM Run this once after copying the project folder to a new Windows machine.
REM Verifies Python, installs deps, sanity-checks ffmpeg, seeds .env.
REM
REM Safe to re-run: skips anything that's already in place.
REM ============================================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo === FarmOps setup ===
echo.

REM 1) Python
REM    Strict check: on Windows the Microsoft Store "App execution alias" puts a
REM    stub python.exe on PATH that just prints "Python was not found..." and
REM    exits successfully from `where python`'s point of view. So we run actual
REM    Python code -- if it errors, real Python isn't installed.
echo Checking Python...
python -c "import sys" >nul 2>&1
if errorlevel 1 (
    echo   [X] Python is NOT installed.
    echo       Windows may be showing the Microsoft Store alias on PATH instead.
    echo.
    echo   Install Python 3.10 or newer:
    echo     - https://python.org/downloads/   ^(direct download, recommended^)
    echo     - or:  winget install Python.Python.3.13
    echo.
    echo   During install, TICK "Add python.exe to PATH".
    echo   After install: CLOSE this terminal, open a new one, then re-run setup.bat.
    echo.
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set "PYVER=%%v"
echo   [OK] Python !PYVER!

REM 2) pip + project deps
echo.
echo Installing Python dependencies (websockets, requests)...
python -m pip install --upgrade pip >nul 2>&1
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo   [X] pip install failed. See output above.
    pause
    exit /b 1
)
echo   [OK] dependencies installed

REM 3) ffmpeg (used by app.py to re-mux uploaded videos so IG doesn't reject them)
echo.
echo Checking ffmpeg + ffprobe...
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo   [!] ffmpeg is NOT on PATH.
    echo       Posting works for videos that are already valid, but the
    echo       duration-fix re-mux will be skipped. Install with:
    echo           winget install Gyan.FFmpeg
) else (
    echo   [OK] ffmpeg
)
where ffprobe >nul 2>&1
if errorlevel 1 (
    echo   [!] ffprobe missing -- comes with ffmpeg install above.
) else (
    echo   [OK] ffprobe
)

REM 4) .env from template
echo.
if exist .env (
    echo .env already present, leaving it alone.
) else (
    if exist .env.example (
        copy /Y .env.example .env >nul
        echo Created .env from .env.example.
        echo   ^>^>^> Open .env and paste your GEMINI_API_KEY before using Smart Comment.
    ) else (
        echo no .env.example found -- skipping.
    )
)

REM 5) Reminder + next steps
echo.
echo === Setup finished ===
echo.
echo Before triggering automations, make sure the Laixi desktop app is running
echo - it provides the WebSocket at ws://127.0.0.1:22221/ that the dashboard talks to.
echo.
echo To start the dashboard:
echo     .\dashboard.bat start
echo.
echo Then open in a browser:
echo     http://127.0.0.1:8000/index.html
echo.
endlocal
exit /b 0
