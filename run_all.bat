@echo off
setlocal enabledelayedexpansion

REM ==========================================================
REM  One-click runner (API + Web UI) - no Python Launcher required
REM  Save as: C:\HuynhCongTuan\Project_AdmissionCheck\run_all_windows.bat
REM ==========================================================

cd /d %~dp0

REM --- (Optional) hardcode your Python 3.12 path here if you know it ---
REM set PY312_EXE=C:\Users\ASUS\AppData\Local\Programs\Python\Python312\python.exe

REM --- Find Python 3.12 executable ---
set "PYEXE="

if not "%PY312_EXE%"=="" if exist "%PY312_EXE%" set "PYEXE=%PY312_EXE%"

if "%PYEXE%"=="" if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PYEXE=%LocalAppData%\Programs\Python\Python312\python.exe"
if "%PYEXE%"=="" if exist "C:\Program Files\Python312\python.exe" set "PYEXE=C:\Program Files\Python312\python.exe"
if "%PYEXE%"=="" if exist "C:\Program Files (x86)\Python312\python.exe" set "PYEXE=C:\Program Files (x86)\Python312\python.exe"

REM If Python Launcher exists, we can still use it
where py >nul 2>&1
if "%PYEXE%"=="" if not errorlevel 1 (
  REM test py -3.12 existence
  py -3.12 -c "import sys; print(sys.version)" >nul 2>&1
  if not errorlevel 1 set "PYEXE=py -3.12"
)

if "%PYEXE%"=="" (
  echo [ERROR] Khong tim thay Python 3.12.
  echo  - Cai Python 3.12 (tick "Add to PATH") hoac
  echo  - Sua file .bat: gan bien PY312_EXE=duong_dan_den_python312\python.exe
  echo Vi du: set PY312_EXE=C:\Users\ASUS\AppData\Local\Programs\Python\Python312\python.exe
  pause
  exit /b 1
)

REM --- Ensure venv is Python 3.12 (recreate if not 3.12) ---
if exist ".venv\Scripts\python.exe" (
  for /f "tokens=2 delims==" %%v in ('findstr /b /c:"version = " .venv\pyvenv.cfg 2^>nul') do set VENV_VER=%%v
  echo %VENV_VER% | findstr /c:"3.12" >nul
  if errorlevel 1 (
    echo [Setup] Found venv not 3.12 -> removing...
    rmdir /s /q .venv
  )
)

if not exist ".venv\Scripts\activate.bat" (
  echo [Setup] Creating venv with Python 3.12...
  if /I "%PYEXE:~0,2%"=="py" (
    py -3.12 -m venv .venv
  ) else (
    "%PYEXE%" -m venv .venv
  )
)

call .venv\Scripts\activate.bat

REM --- Config (edit if needed) ---
if "%DB_URL%"=="" set DB_URL=mysql+pymysql://admission_user:StrongPass123@localhost:3306/admission_check?charset=utf8mb4
REM  ^ Neu Laragon dung 3307, doi :3306 -> :3307
if "%FONT_PATH%"=="" set "FONT_PATH=%cd%\assets\DejaVuSans.ttf"
set API_PORT=8000

REM --- Install deps once ---
if not exist ".venv\installed.flag" (
  echo [Setup] Installing requirements...
  python -m pip install --upgrade pip setuptools wheel
  pip install -r requirements.txt || goto :piperror
  echo ok> .venv\installed.flag
)

REM --- Start API in new window ---
echo [Run] Starting API at http://127.0.0.1:%API_PORT% ...
start "Admissions API" cmd /k "set DB_URL=%DB_URL% && set FONT_PATH=%FONT_PATH% && python -m uvicorn app.main:app --reload --port %API_PORT%"

REM Small delay for API to boot
timeout /t 2 >nul

REM --- Open Web UI ---
set "WEB_INDEX=%cd%\web\index.html"
if exist "%WEB_INDEX%" (
  start "" "%WEB_INDEX%"
) else (
  echo [Warn] web\index.html not found. Please place the UI file there.
)

REM (Optional) Open FastAPI docs
start "" "http://127.0.0.1:%API_PORT%/docs"
exit /b 0

:piperror
echo [Error] Failed to install requirements. Kiem tra mang/permissions hoac requirements.txt.
pause
exit /b 1
