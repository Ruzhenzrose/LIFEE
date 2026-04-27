@echo off
setlocal
cd /d "%~dp0"

echo [LIFEE] Checking port 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    echo [LIFEE] Killing stale PID %%a
    taskkill /F /PID %%a >nul 2>&1
)

if not exist data mkdir data >nul 2>&1

REM Try to pull latest DB from prod (5s timeout). If SSH fails, use local data\lifee.db.
REM First-time users without a local DB: FastAPI will create an empty schema on startup.
echo [LIFEE] Trying to sync prod DB (5s timeout)...
ssh -o ConnectTimeout=5 -o BatchMode=yes root@47.83.184.82 "sqlite3 /opt/lifee/data/lifee.db \".backup /tmp/lifee_snapshot.db\"" >nul 2>&1
if errorlevel 1 (
    echo [LIFEE] SSH unavailable, using existing data\lifee.db.
) else (
    del /q data\lifee.db-wal data\lifee.db-shm >nul 2>&1
    scp -o ConnectTimeout=10 -o BatchMode=yes root@47.83.184.82:/tmp/lifee_snapshot.db data\lifee.db >nul 2>&1
    if errorlevel 1 (
        echo [LIFEE] scp failed, using existing data\lifee.db.
    ) else (
        echo [LIFEE] Synced fresh prod snapshot.
    )
)

echo [LIFEE] Starting backend in a new window (uvicorn with --reload)...
REM StatReload polling is used; do NOT pip install watchfiles (segfaults on Python 3.13).
start "LIFEE backend" cmd /k "cd /d %~dp0 && uvicorn lifee.api:app --host 127.0.0.1 --port 8000 --reload"

echo [LIFEE] Waiting 3s for server to boot...
timeout /t 3 /nobreak >nul

echo [LIFEE] Opening browser at http://localhost:8000/void/
start "" "http://localhost:8000/void/"

echo [LIFEE] Done. Close the backend window to stop.
timeout /t 2 /nobreak >nul
endlocal
