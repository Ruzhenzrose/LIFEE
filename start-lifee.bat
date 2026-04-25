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

echo [LIFEE] Pulling latest DB from server (consistent snapshot via sqlite .backup)...
if not exist data mkdir data >nul 2>&1
REM 先在服务器端跑 .backup，把 main + WAL 合并成一个独立快照文件再拉。
REM 直接 scp lifee.db 会拿到 stale 主文件（活跃的写都在 -wal 里），sqlite .backup
REM 走 SQLite API 拿一致性快照，不依赖 WAL 状态。
ssh -o ConnectTimeout=5 -o BatchMode=yes root@47.83.184.82 "sqlite3 /opt/lifee/data/lifee.db \".backup /tmp/lifee_snapshot.db\"" 2>nul
if errorlevel 1 (
    echo [LIFEE] WARNING: snapshot failed — using existing local DB instead.
) else (
    REM 干掉本地残留 WAL/SHM，避免覆盖主文件后跟旧 WAL 错位。
    del /q data\lifee.db-wal data\lifee.db-shm 2>nul
    scp -o ConnectTimeout=5 -o BatchMode=yes root@47.83.184.82:/tmp/lifee_snapshot.db data\lifee.db
    if errorlevel 1 (
        echo [LIFEE] WARNING: scp failed — using existing local DB instead.
    ) else (
        echo [LIFEE] DB synced from production.
    )
)

echo [LIFEE] Starting backend in a new window (uvicorn with --reload)...
REM --reload: safe because watchfiles is NOT installed; uvicorn falls back to
REM StatReload (stat-based polling) which does not segfault on Python 3.13.
REM If you ever `pip install watchfiles`, drop --reload or the backend may crash.
start "LIFEE backend" cmd /k "cd /d %~dp0 && uvicorn lifee.api:app --host 127.0.0.1 --port 8000 --reload"

echo [LIFEE] Waiting 3s for server to boot...
timeout /t 3 /nobreak >nul

echo [LIFEE] Opening browser at http://localhost:8000/void/
start "" "http://localhost:8000/void/"

echo.
echo [LIFEE] Running. Leave the backend window open while you use the site.
echo [LIFEE] To shut down: close the backend window, or run stop-lifee.bat.
timeout /t 2 /nobreak >nul
endlocal
