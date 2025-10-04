@echo off
setlocal
cd /d "%~dp0"

echo ==============================================
echo  AdmissionCheck - FastAPI runner (Windows)
echo  Folder: %CD%
echo ==============================================

REM ---- Chon Python tao venv ----
where py >nul 2>nul
if %errorlevel%==0 (
  set "PY_BOOT=py -3"
) else (
  set "PY_BOOT=python"
)

REM ---- Tao venv neu chua co ----
if not exist ".venv\Scripts\python.exe" (
  echo [*] Creating virtualenv .venv ...
  %PY_BOOT% -m venv .venv
  if errorlevel 1 (
    echo [x] Tao venv that bai.
    pause
    exit /b 1
  )
)

set "VENV_PY=.venv\Scripts\python.exe"

echo [*] Ensuring pip is up-to-date...
"%VENV_PY%" -m pip install --upgrade pip >nul

if exist requirements.txt (
  echo [*] Installing requirements.txt ...
  "%VENV_PY%" -m pip install -r requirements.txt
)

REM ---- Nhap HOST/PORT ----
set "HOST_DEFAULT=127.0.0.1"
set "PORT_DEFAULT=8000"

set /p HOST=Host [%HOST_DEFAULT%]: 
if "%HOST%"=="" set "HOST=%HOST_DEFAULT%"

set /p PORT=Port [%PORT_DEFAULT%]: 
if "%PORT%"=="" set "PORT=%PORT_DEFAULT%"

echo.
echo [*] Starting server on %HOST%:%PORT% (reload) ...
echo     CTRL+C de dung.

REM ---- Chay uvicorn tu venv ----
"%VENV_PY%" -m uvicorn app.main:app --reload --host %HOST% --port %PORT%
endlocal
