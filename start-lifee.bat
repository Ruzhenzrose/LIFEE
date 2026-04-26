@echo off
setlocal
cd /d "%~dp0"

echo [LIFEE] Checking port 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    echo [LIFEE] Killing stale PID %%a
    taskkill /F /PID %%a >nul 2>&1
)

if not exist data mkdir data >nul 2>&1

echo [LIFEE] Starting backend...
start "LIFEE backend" cmd /k "cd /d "%~dp0" && uvicorn lifee.api:app --host 127.0.0.1 --port 8000 --reload"

echo [LIFEE] Waiting 3s for server to boot...
timeout /t 3 /nobreak >nul

echo [LIFEE] Opening browser at http://localhost:8000/void/
start "" "http://localhost:8000/void/"

echo [LIFEE] Done. Close the backend window to stop.
timeout /t 2 /nobreak >nul
endlocal