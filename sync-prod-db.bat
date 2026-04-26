@echo off
REM Pull a CONSISTENT snapshot of prod DB to local data/lifee.db.
REM 仅 admin（有 SSH key 到生产服务器）使用。队友不要跑这个，因为：
REM   1. 没 SSH key，连不上
REM   2. 拉到的是真实用户数据（邮箱、密码哈希、聊天记录），属于生产隐私
REM
REM 用 sqlite3 .backup 在服务器端先 dump 出快照再 scp，不会拿到 stale 主文件
REM （活跃写都在 -wal 里，直接 scp lifee.db 主文件可能是空的）。
setlocal
cd /d "%~dp0"
if not exist data mkdir data >/dev/null 2>&1

echo [SYNC] Snapshotting prod DB on server...
ssh -o ConnectTimeout=5 root@47.83.184.82 "sqlite3 /opt/lifee/data/lifee.db \".backup /tmp/lifee_snapshot.db\""
if errorlevel 1 (
    echo [SYNC] FAILED: SSH snapshot step. Check VPN / SSH key.
    pause
    exit /b 1
)

REM 干掉本地残留 WAL/SHM，避免覆盖主文件后跟旧 WAL 错位。
del /q data\lifee.db-wal data\lifee.db-shm 2>/dev/null

echo [SYNC] Copying snapshot down...
scp -o ConnectTimeout=10 root@47.83.184.82:/tmp/lifee_snapshot.db data\lifee.db
if errorlevel 1 (
    echo [SYNC] FAILED: scp step.
    pause
    exit /b 1
)

echo [SYNC] Done. Local data\lifee.db now matches prod (snapshot at this moment).
pause
endlocal
