@echo off
chcp 65001 >nul
echo Запуск WebSocket сервера...
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -Command "& '%~dp0venv\Scripts\python.exe' websocket_server.py"
pause
