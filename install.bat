@echo off
setlocal enabledelayedexpansion

REM Detect Python
where python >nul 2>nul
if errorlevel 1 (
  echo Python not found in PATH. Please install Python 3.11+ and retry.
  pause
  exit /b 1
)

REM Create venv if missing
if not exist "venv\Scripts\python.exe" (
  echo Creating virtual environment...
  python -m venv venv
)

REM Upgrade pip
"venv\Scripts\python.exe" -m pip install --upgrade pip

REM Install requirements
echo Installing dependencies from requirements.txt...
"venv\Scripts\pip.exe" install -r requirements.txt

echo.
echo Done. To run the app:
echo   run_smartbell.bat
echo or
echo   venv\Scripts\python.exe Begin.py
pause

