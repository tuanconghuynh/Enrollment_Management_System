@echo off
REM ===============================
REM Run FastAPI Server for AdmissionCheck
REM ===============================

cd /d "%~dp0"

REM --- Activate virtual environment ---
call .venv\Scripts\activate.bat

REM --- Run server ---
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

REM --- Keep window open after exit ---
pause
