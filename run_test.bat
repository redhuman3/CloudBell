@echo off
chcp 65001 >nul
echo Запуск тестового приймача...
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -Command "& '%~dp0venv\Scripts\python.exe' test_stream.py"
pause
