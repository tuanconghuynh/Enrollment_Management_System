@echo off
setlocal
set "PORT=%1"
if "%PORT%"=="" set "PORT=8000"

echo Dung tien trinh LISTEN tren port %PORT% ...

rem --- Thu PowerShell (Windows 10+) ---
powershell -NoProfile -Command ^
  "try {Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction Stop ^| %%{taskkill /F /PID $_.OwningProcess}} catch {exit 1}" >nul 2>&1
if not errorlevel 1 (
  echo [OK] Da dung bang PowerShell.
  goto :done
)

rem --- Fallback netstat ---
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%PORT% .*LISTENING"') do (
  echo Kill PID %%P
  taskkill /F /PID %%P >nul 2>&1
)

:done
echo Xong.
endlocal
