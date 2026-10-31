@echo off
setlocal
cd /d "%~dp0"

echo Stopping Video2X CLI client...
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *cli.py*" 2>nul
taskkill /F /FI "IMAGENAME eq python.exe" /FI "COMMANDLINE eq *cli.py*" 2>nul

REM Kill any python process running cli.py
for /f "tokens=2" %%a in ('tasklist /FI "IMAGENAME eq python.exe" /FO CSV /NH 2^>nul') do (
    wmic process where "ProcessId=%%~a" get CommandLine 2>nul | findstr /I "cli.py" >nul
    if not errorlevel 1 taskkill /F /PID %%~a 2>nul
)

echo Done. (Colab backend: stop by interrupting the cell in your browser.)
pause