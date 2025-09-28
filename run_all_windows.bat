@echo off
setlocal EnableDelayedExpansion

REM ==========================================================
REM  One-click runner (API + Web UI) — FAST
REM ==========================================================
cd /d %~dp0

REM --- toggles ---
set RELOAD=1            REM 1: uvicorn --reload, 0: run thường (nhanh & ổn định hơn)
set SKIP_PIP=0          REM 1: bỏ qua bước pip install luôn

REM --- (Optional) hardcode Python 3.12 path ---
REM set PY312_EXE=C:\Users\ASUS\AppData\Local\Programs\Python\Python312\python.exe

REM --- Find Python 3.12 ---
set "PYEXE="
if not "%PY312_EXE%"=="" if exist "%PY312_EXE%" set "PYEXE=%PY312_EXE%"
if "%PYEXE%"=="" if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PYEXE=%LocalAppData%\Programs\Python\Python312\python.exe"
if "%PYEXE%"=="" if exist "C:\Program Files\Python312\python.exe" set "PYEXE=C:\Program Files\Python312\python.exe"
if "%PYEXE%"=="" if exist "C:\Program Files (x86)\Python312\python.exe" set "PYEXE=C:\Program Files (x86)\Python312\python.exe"
where py >nul 2>&1
if "%PYEXE%"=="" if not errorlevel 1 (
  py -3.12 -c "import sys" >nul 2>&1 && set "PYEXE=py -3.12"
)
if "%PYEXE%"=="" (
  echo [ERROR] Khong tim thay Python 3.12. Cai dat va tick "Add to PATH".
  pause
  exit /b 1
)

REM --- Ensure venv exists (khong xoa-lap lai nua) ---
if not exist ".venv\Scripts\activate.bat" (
  echo [Setup] Tao venv voi Python 3.12...
  if /I "%PYEXE:~0,2%"=="py" (
    py -3.12 -m venv .venv
  ) else (
    "%PYEXE%" -m venv .venv
  )
)
call .venv\Scripts\activate.bat

REM --- Env config ---
if "%DB_URL%"=="" set DB_URL=mysql+pymysql://root:@localhost:3306/admission_check?charset=utf8mb4
if "%FONT_PATH%"=="" set "FONT_PATH=%cd%\assets\TimesNewRoman.ttf"
if "%FONT_PATH_BOLD%"=="" set "FONT_PATH_BOLD=%cd%\assets\TimesNewRoman-Bold.ttf"
set API_PORT=8000

REM --- Tăng tốc pip: dùng cache cục bộ cho dự án ---
set "PIP_CACHE_DIR=%cd%\.venv\pip-cache"

REM --- Cài deps CHỈ khi requirements.txt thay đổi ---
set "REQ_HASH_FILE=.venv\req.hash"
for /f %%H in ('powershell -NoProfile -Command "(Get-FileHash ''requirements.txt'' -Algorithm SHA1).Hash"') do set REQ_HASH=%%H

if "%SKIP_PIP%"=="1" goto :skipdeps
if not exist "%REQ_HASH_FILE%" goto :installdeps
set /p OLD_HASH=<"%REQ_HASH_FILE%"
if /I not "%REQ_HASH%"=="%OLD_HASH%" goto :installdeps
goto :skipdeps

:installdeps
echo [Setup] Installing/Updating requirements (only-if-needed)...
python -m pip install --upgrade pip setuptools wheel --disable-pip-version-check >nul
pip install --upgrade --upgrade-strategy only-if-needed ^
  --disable-pip-version-check -r requirements.txt || goto :piperror
> "%REQ_HASH_FILE%" echo %REQ_HASH%
:skipdeps

REM --- Nếu API đã chạy thì không start thêm ---
set API_OK=
for /f %%S in ('powershell -NoProfile -Command "try{(Invoke-WebRequest -UseBasicParsing ''http://127.0.0.1:%API_PORT%/openapi.json'' -TimeoutSec 1).StatusCode}catch{0}"') do set API_OK=%%S
if "%API_OK%"=="200" (
  echo [Run] API da chay tren cong %API_PORT%.
  goto :openui
)

REM --- Start API ---
echo [Run] Starting API at http://127.0.0.1:%API_PORT% ...
if "%RELOAD%"=="1" (
  start "Admissions API" cmd /k "set DB_URL=%DB_URL% && set FONT_PATH=%FONT_PATH% && set FONT_PATH_BOLD=%FONT_PATH_BOLD% && python -m uvicorn app.main:app --reload --port %API_PORT%"
) else (
  start "Admissions API" cmd /k "set DB_URL=%DB_URL% && set FONT_PATH=%FONT_PATH% && set FONT_PATH_BOLD=%FONT_PATH_BOLD% && python -m uvicorn app.main:app --port %API_PORT%"
)

REM --- mở UI ---
:openui
set "WEB_INDEX=%cd%\web\index.html"
if exist "%WEB_INDEX%" start "" "%WEB_INDEX%"
start "" "http://127.0.0.1:%API_PORT%/docs"
exit /b 0

:piperror
echo [Error] Failed to install requirements. Kiem tra mang/permissions hoac requirements.txt.
pause
exit /b 1
