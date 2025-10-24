# 🎵 Інтеграція з Volumio на Raspberry Pi

## Опис

CloudBell App може транслювати звук безпосередньо в Volumio на Raspberry Pi, який працює як музичний центр. Це дозволяє відтворювати дзвінки на віддаленому пристрої через інтернет.

## Як це працює

```
[CloudBell App на ПК] → [WebSocket Server] → [Volumio на Raspberry Pi]
```

1. CloudBell App захоплює звук
2. Відправляє через WebSocket сервер
3. Volumio отримує та відтворює через Geekworm X302 HiFi DAC HAT

## Варіанти інтеграції

### Варіант 1: MPD (рекомендовано)

Volumio використовує MPD (Music Player Daemon). Можна відправляти аудіо безпосередньо до MPD.

**Переваги:**
- ✅ Нативна підтримка в Volumio
- ✅ Стабільна робота
- ✅ Низька затримка

**Як налаштувати:**

1. В CloudBell App використовуйте URL MPD:
```
ws://your-volumio-ip:6600
```

2. Volumio автоматично відтворить аудіо

### Варіант 2: HTTP Stream

Надішліть аудіо через HTTP потік.

**Код для CloudBell App:**

```python
# В websocket_client додайте HTTP streaming:
import subprocess

def stream_to_volumio_http(audio_data):
    # Створюємо HTTP stream
    url = f"http://your-volumio-ip:8080/api/v1/playuri/"
    requests.post(url, data={
        'uri': audio_data,
        'service': 'mpd'
    })
```

### Варіант 3: DLNA/UPnP

Використовуйте DLNA для відтворення.

**Бібліотека:**
```bash
pip install pydlnadlna-scanner
```

**Код:**
```python
from pydlnadlna import DLNADevice

device = DLNADevice("http://your-volumio-ip:8090")
device.renderer.play(stream_url)
```

## Налаштування WebSocket сервера для Volumio

Оновіть `websocket_server.py`:

```python
import asyncio
import websockets
import json
import logging

logging.basicConfig(level=logging.INFO)

CONNECTED_CLIENTS = set()

async def handler(websocket, path):
    """
    Обробник WebSocket з'єднань для Volumio.
    """
    CONNECTED_CLIENTS.add(websocket)
    logging.info(f"Нове підключення: {websocket.remote_address}")
    
    try:
        async for message in websocket:
            data = json.loads(message)
            
            if data.get('type') == 'audio':
                # Кодуємо в base64
                audio_data = data['data']
                
                # Пересилаємо всім підключеним клієнтам (включаючи Volumio)
                for client in CONNECTED_CLIENTS:
                    if client != websocket:
                        await client.send(message)
                        
            elif data.get('type') == 'control':
                # Команди управління для Volumio
                command = data.get('command')
                if command == 'play':
                    # Запуск відтворення на Volumio
                    pass
                elif command == 'stop':
                    # Зупинка відтворення
                    pass
                    
    except websockets.exceptions.ConnectionClosedOK:
        logging.info("Клієнт відключився")
    finally:
        CONNECTED_CLIENTS.remove(websocket)

async def main():
    port = 8765
    async with websockets.serve(handler, "0.0.0.0", port):
        logging.info(f"WebSocket сервер запущено на ws://0.0.0.0:{port}")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
```

## Налаштування Volumio

### 1. Встановіть WebSocket клієнт на Raspberry Pi

Створіть `volumio_receiver.py`:

```python
import websockets
import asyncio
import json
import subprocess
import logging

logging.basicConfig(level=logging.INFO)

VOLUMIO_API = "http://localhost:3000/api/v1/"
CLOUD_SERVER_URL = "ws://your-cloud-server:8765"

async def receive_and_play():
    """
    Отримує аудіо з CloudBell App та відтворює через Volumio.
    """
    try:
        async with websockets.connect(CLOUD_SERVER_URL) as websocket:
            logging.info("Підключено до CloudBell App")
            
            async for message in websocket:
                data = json.loads(message)
                
                if data.get('type') == 'audio':
                    # Зберігаємо аудіо в тимчасовий файл
                    audio_data = data['data']
                    temp_file = "/tmp/cloudbell_audio.mp3"
                    
                    with open(temp_file, 'wb') as f:
                        f.write(audio_data)
                    
                    # Відтворюємо через Volumio API
                    import requests
                    requests.post(
                        f"{VOLUMIO_API}replaceAndPlay",
                        json={"value": temp_file}
                    )
                    
                    logging.info("Аудіо відтворено через Volumio")
                    
    except Exception as e:
        logging.error(f"Помилка: {e}")

if __name__ == "__main__":
    asyncio.run(receive_and_play())
```

### 2. Встановіть залежності

```bash
pip install websockets requests
```

### 3. Запустіть ресивер

```bash
python volumio_receiver.py
```

## Альтернатива: SSH + MPD

Можна використовувати SSH для відправки файлів:

```python
import paramiko

def send_to_volumio(audio_file):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect('your-volumio-ip', username='volumio', password='volumio')
    
    # Копіюємо файл
    sftp = ssh.open_sftp()
    sftp.put(audio_file, '/tmp/cloudbell.mp3')
    sftp.close()
    
    # Відтворюємо через MPD
    ssh.exec_command('mpc add /tmp/cloudbell.mp3')
    ssh.exec_command('mpc play')
    ssh.close()
```

## Переваги використання Volumio

- ✅ Професійна якість звуку через Geekworm X302 HiFi DAC HAT
- ✅ Низький рівень шуму та спотворень
- ✅ Велика потужність виходу для колонок
- ✅ Стабільна робота 24/7
- ✅ Веб-інтерфейс для управління
- ✅ Підтримка різних форматів аудіо

## Налаштування безпеки

Для публічного доступу:

1. Використовуйте VPN або SSH тунель
2. Додайте автентифікацію в WebSocket
3. Обмежте доступ по IP
4. Використовуйте WSS (зашифрований протокол)

## Тестування

1. Запустіть CloudBell App на ПК
2. Запустіть WebSocket сервер
3. Запустіть `volumio_receiver.py` на Raspberry Pi
4. Натисніть "Почати трансляцію" в CloudBell App
5. Звук повинен відтворитися через Volumio

## Підтримка форматів

Volumio підтримує:
- MP3
- WAV
- FLAC
- OGG

CloudBell App може конвертувати аудіо перед відправкою.

## Оптимізація

Для кращої якості:
- Збільште buffer size до 4096
- Використовуйте FLAC для високої якості
- Налаштуйте приоритет процесу на Raspberry Pi

