@echo off
setlocal
title AdmissionCheck - FastAPI Server (NO VENV)

rem ==== Config ====
set APP=app.main:app
set HOST=0.0.0.0
set PORT=%1
if "%PORT%"=="" set PORT=8000

cd /d "%~dp0"

rem ==== Show versions ====
for /f %%i in ('py -c "import sys;print(sys.version.split()[0])"') do set PYVER=%%i
for /f %%i in ('py -c "import uvicorn,sys;print(uvicorn.__version__)" 2^>nul') do set UVIVER=%%i

echo =================================================
echo Python %PYVER%
if defined UVIVER echo uvicorn %UVIVER%
echo App  : %APP%
echo Host : %HOST%
echo Port : %PORT%
echo =================================================
echo.

rem ==== Canh bao neu port dang ban ====
set PID=
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr LISTENING') do set PID=%%a
if defined PID (
  echo [WARN] Port %PORT% dang duoc su dung boi PID %PID%.
  echo        Chay "stop_server.bat %PORT%" de giai phong port roi chay lai.
  echo.
  pause
  exit /b 1
)

rem ==== Tu dong cai requirements neu co file ====
if exist requirements.txt (
  echo [INFO] Cai/Cap nhat requirements...
  py -m pip install -r requirements.txt
  echo.
)

rem ==== Chay server ====
set CMD=py -m uvicorn %APP% --host %HOST% --port %PORT% --reload
cmd /K %CMD%
endlocal
