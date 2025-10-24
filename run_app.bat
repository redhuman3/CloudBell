@echo off
chcp 65001 >nul
echo Запуск CloudBell App...
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -Command "& '%~dp0venv\Scripts\python.exe' Begin.py"
pause
