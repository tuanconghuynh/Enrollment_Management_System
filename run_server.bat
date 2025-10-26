@echo off
@echo off
chcp 65001 >nul
setlocal ENABLEDELAYEDEXPANSION
cd /d "%~dp0"

echo ==============================================
echo  Admission_Management_System - FastAPI (interactive)
echo  Tao venv + cai thu vien + chay server
echo ==============================================

REM --- Chon Python ---
where py >nul 2>nul && (set "PY=py -3") || (set "PY=python")

REM --- Tao venv neu chua co ---
if not exist ".venv\Scripts\python.exe" (
  echo [*] Creating .venv ...
  %PY% -m venv .venv
)
set "VENV_PY=.venv\Scripts\python.exe"

echo [*] Upgrade pip ...
"%VENV_PY%" -m pip install --upgrade pip >nul

REM --- Cai dat requirements neu chua co thu vien ---
if exist requirements.txt (
  echo [*] Checking & installing dependencies ...
  "%VENV_PY%" -m pip install --no-cache-dir -r requirements.txt
) else (
  echo [!] Khong tim thay file requirements.txt
)

REM --- Hien menu chon host mode ---
echo.
echo ==============================================
echo =======   CHỌN CHẾ ĐỘ KẾT NỐI SERVER   =======
echo ==============================================
echo  [1] Máy cá nhân (Local Only)
echo      → Chỉ truy cập được trên máy này
echo.
echo  [2] Dùng mạng LAN (Local Network)
echo      → Cho phép máy khác trong cùng mạng truy cập
echo        * Nhập IPv4 của máy (VD: 192.168.x.xx)
echo ==============================================

choice /c 12 /n /m "  → Chọn chế độ (1/2): "
set "MODE=%errorlevel%"

set "APP_PORT=8000"
set /p APP_PORT=Nhap PORT [8000]: 
if "%APP_PORT%"=="" set "APP_PORT=8000"

if "%MODE%"=="1" (
  set "APP_HOST=127.0.0.1"
  set "OPEN_HOST=127.0.0.1"
  echo [i] Che do Local: mo http://127.0.0.1:%APP_PORT%/
) else (
  echo [i] Che do LAN: may khac co the truy cap
  set /p LAN_IP=Nhap IP LAN [vi du 192.168.2.82]: 
  if "%LAN_IP%"=="" set "LAN_IP=127.0.0.1"
  set "APP_HOST=0.0.0.0"
  set "OPEN_HOST=%LAN_IP%"
  echo [i] Server bind: 0.0.0.0  —  Truy cap: http://%LAN_IP%:%APP_PORT%/
)

echo.
echo [*] Using settings:
echo    APP_HOST=%APP_HOST%
echo    APP_PORT=%APP_PORT%
echo    OPEN_HOST(for browser)=%OPEN_HOST%

REM --- Tu dong mo trinh duyet khi server san sang ---
where curl >nul 2>nul
if %errorlevel%==0 (
  start "" cmd /c "setlocal EnableDelayedExpansion & for /l %%i in (1,1,25) do (curl -s -o nul -m 1 http://%OPEN_HOST%:%APP_PORT%/ && (start "" http://%OPEN_HOST%:%APP_PORT%/ & exit /b) & timeout /t 1 >nul ) & endlocal"
) else (
  start "" cmd /c "timeout /t 2 >nul & start http://%OPEN_HOST%:%APP_PORT%/"
)

echo.
echo [*] Starting server (reload) ...
echo     Press CTRL+C to stop.
"%VENV_PY%" -m uvicorn app.main:app --reload --host %APP_HOST% --port %APP_PORT%

endlocal
