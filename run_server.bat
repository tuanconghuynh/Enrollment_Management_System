@echo off
setlocal enabledelayedexpansion
title AdmissionCheck - FastAPI Server (stay-open)

REM ==== Config ====
set APP=app.main:app
set HOST=0.0.0.0
set PORT=%1
if "%PORT%"=="" set PORT=8000

cd /d "%~dp0"

REM ==== Kích hoạt venv nếu có ====
if exist ".venv\Scripts\activate.bat" (
  call ".venv\Scripts\activate.bat"
) else if exist "venv\Scripts\activate.bat" (
  call "venv\Scripts\activate.bat"
)

REM ==== Kiểm tra Python ====
where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Khong tim thay "python" trong PATH.
  echo Hay cai dat Python 3.x hoac kich hoat virtualenv truoc.
  echo.
  pause
  exit /b 1
)

REM ==== Cảnh báo nếu port đang bận ====
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr LISTENING') do (
  set PID=%%a
)
if defined PID (
  echo [WARN] Port %PORT% dang duoc su dung boi PID !PID!.
  echo        Chay "stop_server.bat %PORT%" de giai phong port roi chay lai.
  echo.
  pause
  exit /b 1
)

REM ==== (Tuỳ chọn) Cai requirements neu co file ====
if exist requirements.txt (
  echo Dang cai/Cap nhat requirements (neu can)...
  python -m pip install -r requirements.txt
  echo.
)

set CMD=python -m uvicorn %APP% --host %HOST% --port %PORT% --reload

echo ================== RUN SERVER ==================
echo  App  : %APP%
echo  Host : %HOST%
echo  Port : %PORT%
echo  Cmd  : %CMD%
echo =================================================
echo.

REM Dung cmd /K de GIU cua so mo sau khi uvicorn thoat (xem trace loi)
cmd /K %CMD%

echo.
echo [INFO] Uvicorn exited with code %errorlevel%.
echo Nhan phim bat ky de dong cua so...
pause >nul
endlocal
