@echo off
chcp 65001 >nul
echo ================================================
echo CloudBell App - Запуск всіх компонентів
echo ================================================
echo.

echo [1/3] Запуск WebSocket сервера...
start "WebSocket Server" powershell -ExecutionPolicy Bypass -Command "& '%~dp0venv\Scripts\python.exe' websocket_server.py"
timeout /t 2 /nobreak >nul

echo [2/3] Запуск CloudBell App...
start "CloudBell App" powershell -ExecutionPolicy Bypass -Command "& '%~dp0venv\Scripts\python.exe' Begin.py"
timeout /t 2 /nobreak >nul

echo [3/3] Запуск тестового приймача...
start "Test Receiver" powershell -ExecutionPolicy Bypass -Command "& '%~dp0venv\Scripts\python.exe' test_stream.py"

echo.
echo ✅ Всі компоненти запущено!
echo.
echo Окна:
echo - "WebSocket Server" - сервер трансляції
echo - "CloudBell App" - головна програма
echo - "Test Receiver" - тестовий приймач
echo.
echo Інструкція:
echo 1. В CloudBell App натисніть "☁️ Хмарна трансляція"
echo 2. Натисніть "▶️ Почати трансляцію"
echo 3. Подивіться в Test Receiver - мають з'явитися аудіо блоки
echo.
pause
