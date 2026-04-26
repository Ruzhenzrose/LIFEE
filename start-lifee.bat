@echo off
setlocal
cd /d "%~dp0"

echo [LIFEE] Checking port 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    echo [LIFEE] Killing stale PID %%a
    taskkill /F /PID %%a >nul 2>&1
)

if not exist data mkdir data >/dev/null 2>&1

REM 尝试从生产拉一份最新快照；连不上就用本地 data\lifee.db（队友已手动放进去的）。
REM 第一次且 data\lifee.db 也不存在时，FastAPI 会自动建空表，但此时没账号可登录。
echo [LIFEE] Trying to sync prod DB (5s timeout)...
ssh -o ConnectTimeout=5 -o BatchMode=yes root@47.83.184.82 "sqlite3 /opt/lifee/data/lifee.db \".backup /tmp/lifee_snapshot.db\"" >/dev/null 2>&1
if errorlevel 1 (
    echo [LIFEE] SSH unavailable, using existing data\lifee.db.
) else (
    del /q data\lifee.db-wal data\lifee.db-shm >/dev/null 2>&1
    scp -o ConnectTimeout=10 -o BatchMode=yes root@47.83.184.82:/tmp/lifee_snapshot.db data\lifee.db >/dev/null 2>&1
    if errorlevel 1 (
        echo [LIFEE] scp failed, using existing data\lifee.db.
    ) else (
        echo [LIFEE] Synced fresh prod snapshot.
    )
)

echo [LIFEE] Starting backend in a new window (uvicorn with --reload)...
REM --reload 用 StatReload 轮询，watchfiles 在 Python 3.13 上会段错误，别 pip install。
start "LIFEE backend" cmd /k "cd /d %~dp0 && uvicorn lifee.api:app --host 127.0.0.1 --port 8000 --reload"

echo [LIFEE] Waiting 3s for server to boot...
timeout /t 3 /nobreak >nul

echo [LIFEE] Opening browser at http://localhost:8000/void/
start "" "http://localhost:8000/void/"

echo [LIFEE] Done. Close the backend window to stop.
timeout /t 2 /nobreak >nul
endlocal