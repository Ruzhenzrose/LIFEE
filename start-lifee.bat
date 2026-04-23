@echo off
REM LIFEE one-click launcher (Windows)
REM Double-click to start the FastAPI backend and open the web UI in the
REM default browser. Safe to re-run — kills any stale process on port 8000
REM first so the server always comes up clean.
setlocal
cd /d "%~dp0"

echo [LIFEE] Checking port 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    echo [LIFEE] Killing stale PID %%a holding port 8000
    taskkill /F /PID %%a >nul 2>&1
)

echo [LIFEE] Starting backend in a new window (uvicorn, no --reload)...
REM --reload uses watchfiles which segfaults on Python 3.13 on Windows.
start "LIFEE backend" cmd /k "cd /d %~dp0 && uvicorn lifee.api:app --host 127.0.0.1 --port 8000"

echo [LIFEE] Waiting 3s for server to boot...
timeout /t 3 /nobreak >nul

echo [LIFEE] Opening browser at http://localhost:8000/void/
start "" "http://localhost:8000/void/"

echo.
echo [LIFEE] Running. Leave the backend window open while you use the site.
echo [LIFEE] To shut down: close the backend window, or run stop-lifee.bat.
timeout /t 2 /nobreak >nul
endlocal
