@echo off
setlocal ENABLEDELAYEDEXPANSION
cd /d "%~dp0"

echo ==============================================
echo  AdmissionCheck - FastAPI (interactive)
echo  Tao venv + chay server + tu mo trinh duyet
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

if exist requirements.txt (
  echo [*] Installing requirements.txt ...
  "%VENV_PY%" -m pip install -r requirements.txt
)

echo.
echo ===== Chon che do HOST =====
echo  [1] Local only  (de xuat)  -> 127.0.0.1  (chi may anh truy cap)
echo  [2] LAN mode              -> 0.0.0.0  (may khac trong mang truy cap)
choice /c 12 /n /m " 1] Local only  (de xuat)  -> 127.0.0.1  (chi may anh truy cap) hoac [2] LAN mode -> 0.0.0.0  (may khac trong mang truy cap)Chon (1/2): "
set "MODE=%errorlevel%"

set "APP_PORT=8000"
set /p APP_PORT=Nhap PORT [8000]: 
if "%APP_PORT%"=="" set "APP_PORT=8000"

if "%MODE%"=="1" (
  set "APP_HOST=127.0.0.1"
  set "OPEN_HOST=127.0.0.1"
  echo.
  echo [i] Che do Local: trinh duyet se mo http://127.0.0.1:%APP_PORT%/
) else (
  echo.
  echo [i] Che do LAN: may khac trong mang co the truy cap
  echo     Vi du IP LAN: 192.168.2.82  (mo Firewall neu can)
  set "LAN_IP="
  set /p LAN_IP=Nhap IP LAN de mo tren trinh duyet [vi du 192.168.2.82]: 
  if "%LAN_IP%"=="" (
    echo [!] Khong nhap IP -> dung 127.0.0.1 de mo trinh duyet
    set "LAN_IP=127.0.0.1"
  )
  set "APP_HOST=0.0.0.0"
  set "OPEN_HOST=%LAN_IP%"
  echo [i] Server bind: 0.0.0.0
  echo     Truy cap tren may khac: http://%LAN_IP%:%APP_PORT%/
)

echo.
echo [*] Using settings:
echo    APP_HOST=%APP_HOST%
echo    APP_PORT=%APP_PORT%
echo    OPEN_HOST(for browser)=%OPEN_HOST%

REM --- Mo trinh duyet khi server san sang ---
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
