@echo off
echo [INFO] Stopping Uvicorn server...

:: Kill tất cả tiến trình uvicorn.exe đang chạy
taskkill /F /IM uvicorn.exe >nul 2>&1

:: Kill luôn python.exe nếu chạy trực tiếp bằng python -m uvicorn
taskkill /F /IM python.exe >nul 2>&1

echo [INFO] Server stopped.
pause
