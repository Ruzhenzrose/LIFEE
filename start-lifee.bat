@echo off
REM LIFEE one-click launcher (Windows)
REM Double-click to start the FastAPI backend and open the web UI.
REM Safe to re-run — kills any stale process on port 8000 first.
setlocal
cd /d "%~dp0"

echo [LIFEE] Checking port 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    echo [LIFEE] Killing stale PID %%a holding port 8000
    taskkill /F /PID %%a >/dev/null 2>&1
)

REM 第一次启动会自动建空 DB（schema 在 lifee/store.py，首次连接时自建）。
REM 想拉生产数据快照需要 SSH 权限，单独跑 sync-prod-db.bat（仅 admin 用）。
if not exist data mkdir data >/dev/null 2>&1

echo [LIFEE] Starting backend in a new window (uvicorn with --reload)...
REM --reload 用 StatReload 轮询，watchfiles 在 Python 3.13 上会段错误，别 pip install。
start "LIFEE backend" cmd /k "cd /d %~dp0 && uvicorn lifee.api:app --host 127.0.0.1 --port 8000 --reload"

echo [LIFEE] Waiting 3s for server to boot...
timeout /t 3 /nobreak >/dev/null

echo [LIFEE] Opening browser at http://localhost:8000/void/
start "" "http://localhost:8000/void/"

echo.
echo [LIFEE] Running. Leave the backend window open while you use the site.
echo [LIFEE] To shut down: close the backend window, or run stop-lifee.bat.
timeout /t 2 /nobreak >/dev/null
endlocal
