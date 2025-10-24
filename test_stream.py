"""
Простий тест для перевірки хмарної трансляції звуку.
"""
import websockets
import asyncio
import json
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

async def test_receiver():
    """
    Тестовий приймач для перевірки чи приходить аудіо з CloudBell App.
    """
    try:
        uri = "ws://localhost:8765"
        logging.info(f"Підключення до {uri}...")
        
        async with websockets.connect(uri) as websocket:
            logging.info("Підключено до сервера!")
            logging.info("Очікую аудіо дані від CloudBell App...")
            logging.info("ПРИМІТКА: Зараз трансляція працює в демо-режимі")
            logging.info("Реальний стрімінг PyAudio буде реалізовано в наступних версіях")
            
            count = 0
            try:
                # Чекаємо повідомлення, але з таймаутом
                message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                try:
                    data = json.loads(message)
                    if data.get('type') == 'audio':
                        count += 1
                        logging.info(f"Отримано аудіо блок #{count}")
                        logging.info("✅ Тест успішний! Трансляція працює!")
                except Exception as e:
                    logging.error(f"Помилка обробки: {e}")
            except asyncio.TimeoutError:
                logging.warning("Таймаут - не отримано жодних даних")
                logging.info("Це нормально - трансляція в демо-режимі")
                    
    except Exception as e:
        logging.error(f"Помилка підключення: {e}")
        logging.info("Переконайтеся що WebSocket сервер запущений (websocket_server.py)")

if __name__ == "__main__":
    print("=" * 60)
    print("ТЕСТ ХМАРНОЇ ТРАНСЛЯЦІЇ CloudBell App")
    print("=" * 60)
    print("\nІнструкція:")
    print("1. Переконайтеся що websocket_server.py запущений")
    print("2. В CloudBell App натисніть 'Хмарна трансляція'")
    print("3. Натисніть 'Почати трансляцію'")
    print("4. Цей скрипт отримає аудіо дані")
    print("\nВАЖЛИВО: Зараз трансляція працює в демо-режимі!")
    print("Реальний PyAudio стрімінг буде реалізовано пізніше.\n")
    
    asyncio.run(test_receiver())
