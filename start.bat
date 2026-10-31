@echo off
setlocal
cd /d "%~dp0"

if not exist "client\.venv" (
    echo Creating virtual environment...
    python -m venv client\.venv
    if errorlevel 1 (
        echo Python not found. Install Python 3.11+ from python.org
        pause
        exit /b 1
    )
)

echo Installing dependencies...
client\.venv\Scripts\pip install -q -r client\requirements.txt
if errorlevel 1 (
    echo Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo Starting Video2X CLI client...
client\.venv\Scripts\python client\cli.py %*
pause