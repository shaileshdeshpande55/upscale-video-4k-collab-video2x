@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo Python not found. Install Python 3.11+ from python.org
        pause
        exit /b 1
    )
)

echo Installing dependencies...
.venv\Scripts\pip install -q -r requirements.txt
if errorlevel 1 (
    echo Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo Starting Video2X CLI client...
.venv\Scripts\python cli.py %*
pause