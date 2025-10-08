echo.
echo [*] Server stopped.
pause
taskkill /IM python.exe /F >nul 2>nul
endlocal
exit /b
