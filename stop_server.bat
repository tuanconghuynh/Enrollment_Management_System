@echo off
setlocal
title AdmissionCheck - Stop Server

set PORT=%1
if "%PORT%"=="" set PORT=8000

echo.
echo ================== STOP SERVER ==================
echo  Target port: %PORT%
echo =================================================
echo.

set PID=
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr LISTENING') do (
  set PID=%%a
  goto :found
)

:found
if not defined PID (
  echo [INFO] Khong tim thay tien trinh nao LISTEN tren port %PORT%.
  echo Done.
  pause
  goto :eof
)

echo [INFO] Found PID %PID% listening on port %PORT%. Dang kill...
taskkill /PID %PID% /F >nul 2>&1
if errorlevel 1 (
  echo [WARN] taskkill that bai hoac can quyen admin. Thu Run as Administrator.
) else (
  echo [OK] Da dung server (PID %PID%).
)
echo.
pause
endlocal
