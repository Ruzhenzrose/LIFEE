@echo off
REM LIFEE stop — kill whatever is listening on port 8000.
setlocal
set FOUND=0
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    set FOUND=1
    echo [LIFEE] Stopping backend PID %%a
    taskkill /F /PID %%a >nul 2>&1
)
if "%FOUND%"=="0" echo [LIFEE] No backend running on port 8000.
timeout /t 1 /nobreak >nul
endlocal
