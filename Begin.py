# -*- coding: utf-8 -*-
"""
CloudBell App (оновлено):
 - Єдина конфігурація config.json у %APPDATA%/CloudBell
 - Динамічна кількість уроків (можна додавати / видаляти)
 - Окремі звуки для:
      * Початку кожного уроку (кастом або дефолт)
      * Закінчення кожного уроку (кастом або дефолт)
 - Окремий блок звуків тривоги (air_alert, air_clear) і хвилини мовчання
 - Міграція зі старих файлів (schedule.json, friday_schedule.json, sound_settings.json)
 - Трирівневий вибір: область → район → громада (збереження в config)
"""

import os
import sys
import json
import shutil
import time
import datetime
import threading
import logging
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import webbrowser
import pygame
import requests
from requests.structures import CaseInsensitiveDict
from PIL import Image, ImageTk
import pystray
from pystray import MenuItem
from plyer import notification
import tkinter.font as tkfont   # ← ДОДАЛИ
from pathlib import Path
import hashlib
import base64
import uuid
import pyaudio
import websockets
import asyncio
import threading
import queue
import socket
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import io
import queue
try:
    import sounddevice as sd
    import numpy as np
    AUDIO_CAPTURE_AVAILABLE = True
except ImportError:
    AUDIO_CAPTURE_AVAILABLE = False
    sd = None
    np = None

def resource_path(rel_path: str) -> str:
    """
    Повертає абсолютний шлях до ресурсу як у dev, так і в упакованому (--onefile) exe.
    rel_path може бути як 'config/school_logo.png'.
    """
    if hasattr(sys, '_MEIPASS'):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent
    return str((base / rel_path).resolve())

# ----------------------- ЛОГІНГ -----------------------
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")
logging.info("Запуск програми CloudBell App")

# ----------------------- СТАЛІ ------------------------
SPECIAL_EVENT_TIME = datetime.time(9, 0)
API_KEY = "adbeebe5:e2d0f8fccb7fbcefbf305b6eec11493e"

COLORS = {
    'background': '#F8F9FA',
    'primary': '#1A365D',
    'secondary': '#4A5568',
    'text': '#2D3748',
    'alert': '#E53E3E',
    'warning_bg': '#FED7D7',
    'accent': '#3182CE',
    'success': '#38A169',
    'card_bg': '#FFFFFF',
    'border': '#E2E8F0'
}

UKRAINIAN_DAYS = {
    0: "Понеділок", 1: "Вівторок", 2: "Середа",
    3: "Четвер", 4: "П'ятниця", 5: "Субота", 6: "Неділя"
}

UKRAINIAN_MONTHS = {
    1: "Січень", 2: "Лютий", 3: "Березень",
    4: "Квітень", 5: "Травень", 6: "Червень",
    7: "Липень", 8: "Серпень", 9: "Вересень",
    10: "Жовтень", 11: "Листопад", 12: "Грудень"
}

DEFAULT_NORMAL_SCHEDULE = [
    ['08:00', '08:45'], ['08:55', '09:40'],
    ['09:50', '10:35'], ['10:45', '11:30'],
    ['11:40', '12:25'], ['12:40', '13:25'],
    ['13:35', '14:20'], ['14:30', '15:15']
]

DEFAULT_FRIDAY_SCHEDULE = [
    ['08:00', '08:35'], ['08:45', '09:20'],
    ['09:30', '10:05'], ['10:15', '10:50'],
    ['11:00', '11:35'], ['11:45', '12:20'],
    ['12:30', '13:05'], ['13:15', '13:50']
]

# ----------------------- ЛІЦЕНЗУВАННЯ ------------------------
MASTER_SECRET = "CloudBell2025SecretKey"  # Секретний ключ автора

def generate_license_key(organization_name: str, user_email: str) -> str:
    """
    Генерує ліцензійний ключ для організації.
    """
    data = f"{organization_name}|{user_email}|{MASTER_SECRET}"
    hash_obj = hashlib.sha256(data.encode())
    key = base64.b64encode(hash_obj.digest()).decode()[:32]
    return f"CB-{key}"

def validate_license_key(license_key: str) -> tuple[bool, str, str]:
    """
    Перевіряє ліцензійний ключ та повертає (valid, organization, email).
    """
    if not license_key.startswith("CB-"):
        return False, "", ""
    
    try:
        # Читаємо збережену інформацію про ліцензію
        if os.path.exists(LICENSE_FILE):
            with open(LICENSE_FILE, 'r', encoding='utf-8') as f:
                license_data = json.load(f)
                stored_key = license_data.get('key', '')
                organization = license_data.get('organization', '')
                email = license_data.get('email', '')
                
                if stored_key == license_key:
                    return True, organization, email
        
        # Якщо файл не існує, спробуємо валідувати ключ
        # (тут можна додати онлайн валідацію)
        return False, "", ""
    except Exception:
        return False, "", ""

def save_license_info(license_key: str, organization: str, email: str):
    """
    Зберігає інформацію про ліцензію.
    """
    license_data = {
        'key': license_key,
        'organization': organization,
        'email': email,
        'activated_date': datetime.datetime.now().isoformat()
    }
    with open(LICENSE_FILE, 'w', encoding='utf-8') as f:
        json.dump(license_data, f, ensure_ascii=False, indent=2)

# ----------------------- ХМАРНА ТРАНСЛЯЦІЯ ЗВУКУ ------------------------
CLOUD_SERVER_URL = "wss://cloudbell.up.railway.app"  # Публічний сервер на Railway
AUDIO_CHUNK_SIZE = 1024
AUDIO_FORMAT = pyaudio.paInt16
AUDIO_CHANNELS = 1
AUDIO_RATE = 44100

# HTTP Audio Stream Server
class AudioStreamHandler(BaseHTTPRequestHandler):
    """Обробник HTTP запитів для стрімінгу аудіо"""
    
    def do_GET(self):
        try:
            parsed_path = urlparse(self.path)
            
            if parsed_path.path == '/stream':
                query_params = parse_qs(parsed_path.query)
                filename = query_params.get('file', [''])[0]
                
                if not filename:
                    self.send_response(400)
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(b'Missing file parameter')
                    return
                
                # Шукаємо файл
                file_path = self.find_audio_file(filename)
                
                if not file_path or not os.path.exists(file_path):
                    self.send_response(404)
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(b'File not found')
                    return
                
                try:
                    with open(file_path, 'rb') as f:
                        audio_data = f.read()
                    
                    mime_type = self.get_mime_type(filename)
                    
                    # Відправляємо відповідь
                    self.send_response(200)
                    self.send_header('Content-Type', mime_type)
                    self.send_header('Content-Length', str(len(audio_data)))
                    self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
                    self.send_header('Access-Control-Allow-Headers', 'Content-Type')
                    self.end_headers()
                    self.wfile.write(audio_data)
                    
                except Exception as e:
                    self.send_response(500)
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(str(e).encode())
            elif parsed_path.path == '/live' or parsed_path.path == '/live.m3u':
                # Потоковий стрім аудіо
                try:
                    # Для .m3u файлу (плейлист)
                    if parsed_path.path == '/live.m3u':
                        m3u_content = "#EXTM3U\n#EXTINF:-1,CloudBell Live Stream\n/live\n"
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/vnd.apple.mpegurl')
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.end_headers()
                        self.wfile.write(m3u_content.encode('utf-8'))
                    else:
                        # Потоковий MP3 стрім
                        logging.info("[STREAM] Новий клієнт підключився до /live")
                        self.send_response(200)
                        self.send_header('Content-Type', 'audio/mpeg')
                        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.send_header('X-Content-Type-Options', 'nosniff')
                        self.end_headers()
                        
                        # Потоковий відправка аудіо
                        try:
                            chunk_count = 0
                            empty_count = 0
                            while True:
                                try:
                                    # Отримуємо аудіо з буфера (timeout 0.1 секунди)
                                    audio_chunk = audio_buffer.get(timeout=0.1)
                                    empty_count = 0  # Скидаємо лічильник
                                    if audio_chunk:
                                        chunk_count += 1
                                        if chunk_count % 50 == 0:  # Логуємо кожні 50 чанків
                                            logging.info(f"[STREAM] Відправлено {chunk_count} чанків, останній: {len(audio_chunk)} байт")
                                        try:
                                            self.wfile.write(audio_chunk)
                                            self.wfile.flush()
                                        except Exception as write_error:
                                            logging.info(f"[STREAM] Помилка запису: {write_error}")
                                            break
                                except queue.Empty:
                                    empty_count += 1
                                    if empty_count == 100:  # Логуємо кожні 100 порожніх перевірок
                                        logging.debug(f"[STREAM] Буфер порожній, чекаємо аудіо...")
                                        empty_count = 0
                                    # Короткий біт тиші для підтримки з'єднання
                                    time.sleep(0.01)
                                    pass
                        except Exception as e:
                            # Зв'язок розірвано
                            logging.info(f"[STREAM] З'єднання розірвано: {e}")
                            import traceback
                            logging.debug(traceback.format_exc())
                            pass
                            
                except Exception as e:
                    logging.error(f"Помилка потокового стріму: {e}")
            elif parsed_path.path == '/':
                # Отримуємо ngrok URL
                current_url = ngrok_url if ngrok_url else f"http://{get_local_ip()}:{http_server_port}"
                playlist_url = f"{current_url}/live.m3u"
                stream_url = f"{current_url}/live"
                
                # Головна сторінка з потоковим плеєром
                html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CloudBell Audio Stream</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 50px auto;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #fff;
        }}
        .container {{
            background: rgba(255,255,255,0.1);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.37);
        }}
        h1 {{ text-align: center; }}
        .player {{
            background: rgba(0,0,0,0.3);
            padding: 20px;
            border-radius: 10px;
            margin: 20px 0;
            text-align: center;
        }}
        audio {{ width: 100%; }}
        .info {{
            background: rgba(255,255,255,0.2);
            padding: 15px;
            border-radius: 10px;
            margin: 20px 0;
        }}
        .links {{
            background: rgba(0,0,0,0.3);
            padding: 15px;
            border-radius: 10px;
            margin: 15px 0;
        }}
        .link-item {{
            margin: 10px 0;
            padding: 10px;
            background: rgba(0,0,0,0.2);
            border-radius: 5px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        .link-url {{
            flex: 1;
            margin-right: 10px;
            font-family: monospace;
            font-size: 12px;
            word-break: break-all;
            color: #ffd700;
        }}
        .copy-btn {{
            background: #4CAF50;
            color: white;
            border: none;
            padding: 8px 15px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 14px;
        }}
        .copy-btn:hover {{
            background: #45a049;
        }}
        .copy-btn:active {{
            background: #3d8b40;
        }}
        .status {{ text-align: center; font-size: 18px; margin: 10px 0; }}
        a {{ color: #ffd700; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔔 CloudBell Audio Stream</h1>
        <div class="player">
            <div class="status">📻 Прямий ефір дзвінків</div>
            <audio id="streamPlayer" controls autoplay>
                <source src="/live" type="audio/mpeg">
                Ваш браузер не підтримує аудіо поток.
            </audio>
        </div>
        <div class="links">
            <h3 style="margin-top: 0;">🔗 Посилання для стріму:</h3>
            <div class="link-item">
                <span class="link-url" id="playlistUrl">{playlist_url}</span>
                <button class="copy-btn" onclick="copyToClipboard('playlistUrl')">📋 Копіювати</button>
            </div>
            <div class="link-item">
                <span class="link-url" id="streamUrl">{stream_url}</span>
                <button class="copy-btn" onclick="copyToClipboard('streamUrl')">📋 Копіювати</button>
            </div>
        </div>
        <div class="info">
            <h3>📱 Для телефону:</h3>
            <p>Відкрийте <a href="https://raw.githubusercontent.com/redhuman3/CloudBell/main/cloudbell_audio.html" target="_blank">cloudbell_audio.html</a> для автоматичного відтворення дзвінків</p>
        </div>
    </div>
    <script>
        const audio = document.getElementById('streamPlayer');
        audio.addEventListener('error', function() {{
            console.log('Помилка завантаження потоку');
        }});
        
        function copyToClipboard(elementId) {{
            const element = document.getElementById(elementId);
            const text = element.textContent;
            navigator.clipboard.writeText(text).then(function() {{
                // Змінюємо текст кнопки
                const btn = event.target;
                const originalText = btn.textContent;
                btn.textContent = '✅ Скопійовано!';
                btn.style.background = '#45a049';
                setTimeout(function() {{
                    btn.textContent = originalText;
                    btn.style.background = '#4CAF50';
                }}, 2000);
            }}).catch(function(err) {{
                console.error('Помилка копіювання:', err);
            }});
        }}
    </script>
</body>
</html>
                """
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(html.encode('utf-8'))
            else:
                self.send_response(404)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(b'Not Found')
                
        except Exception as e:
            try:
                self.send_response(500)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(str(e).encode())
            except:
                pass
    
    def find_audio_file(self, filename):
        search_paths = [
            os.path.join(CONFIG_DIR, filename),
            os.path.join(os.path.dirname(__file__), filename),
            filename
        ]
        for path in search_paths:
            if os.path.exists(path):
                return path
        return None
    
    def get_mime_type(self, filename):
        ext = os.path.splitext(filename)[1].lower()
        mime_types = {'.mp3': 'audio/mpeg', '.wav': 'audio/wav', '.ogg': 'audio/ogg'}
        return mime_types.get(ext, 'audio/mpeg')
    
    def do_OPTIONS(self):
        """Обробляє OPTIONS запити для CORS"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Max-Age', '86400')
        self.end_headers()
    
    def log_message(self, format, *args):
        pass

def get_local_ip():
    """Отримує локальний IP адресу"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "localhost"

http_server = None
http_server_port = 8765
ngrok_url = None
ngrok_process = None
audio_buffer = queue.Queue(maxsize=10)  # Буфер для потокового аудіо (максимум 10 файлів)
audio_capture_stream = None  # Поток захоплення аудіо

def audio_capture_callback(indata, frames, time_info, status):
    """Callback функція для захоплення аудіо"""
    if status:
        logging.warning(f"[AUDIO_CAPTURE] Status: {status}")
    
    try:
        # Конвертуємо float32 audio data в bytes (16-bit PCM)
        audio_int16 = (indata * 32767).astype(np.int16)
        audio_bytes = audio_int16.tobytes()
        
        # Додаємо до буфера
        send_audio_to_stream(audio_bytes)
    except Exception as e:
        logging.error(f"[AUDIO_CAPTURE] Помилка: {e}")

def start_audio_capture():
    """Запускає захоплення аудіо з вихідного пристрою через WASAPI loopback"""
    global audio_capture_stream
    
    if not AUDIO_CAPTURE_AVAILABLE:
        logging.warning("[AUDIO_CAPTURE] sounddevice не встановлено")
        return False
    
    try:
        # На Windows використовуємо WASAPI loopback для захоплення з динаміків
        devices = sd.query_devices()
        device_id = None
        
        # Шукаємо WASAPI loopback пристрій
        for i, device in enumerate(devices):
            # WASAPI loopback показується як input device
            hostapi_name = str(device.get('hostapi', '')).lower()
            if 'wasapi' in hostapi_name and device['max_input_channels'] > 0:
                # Це loopback пристрій
                device_id = i
                logging.info(f"[AUDIO_CAPTURE] Знайдено WASAPI loopback: {device['name']}")
                break
        
        if device_id is None:
            # Шукаємо "Стерео микшер" або аналогічний loopback пристрій
            for i, device in enumerate(devices):
                device_name_lower = device['name'].lower()
                # Перевіряємо чи це loopback пристрій
                if (device['max_input_channels'] >= 2 and 
                    ('mix' in device_name_lower or 'stereo' in device_name_lower or 
                     'loopback' in device_name_lower or 'вихід' in device_name_lower)):
                    # Пробуємо безпосередньо використовувати пристрій без тесту
                    device_id = i
                    logging.info(f"[AUDIO_CAPTURE] Знайдено потенційний loopback пристрій: {device['name']}")
                    break
        
        if device_id is None:
            logging.error("[AUDIO_CAPTURE] Не вдалося знайти loopback пристрій")
            return False
        
        # Запускаємо захоплення стерео з NOT blocking mode
        audio_capture_stream = sd.InputStream(
            device=device_id,
            channels=2,  # Стерео
            samplerate=44100,
            dtype='float32',
            callback=audio_capture_callback,
            blocksize=2048,
            latency='low'
        )
        
        audio_capture_stream.start()
        logging.info(f"[AUDIO_CAPTURE] Захоплення аудіо запущено на пристрої {device_id}")
        return True
        
    except Exception as e:
        logging.error(f"[AUDIO_CAPTURE] Помилка запуску: {e}")
        import traceback
        logging.debug(traceback.format_exc())
        return False

def stop_audio_capture():
    """Зупиняє захоплення аудіо"""
    global audio_capture_stream
    if audio_capture_stream:
        try:
            audio_capture_stream.stop()
            audio_capture_stream.close()
            audio_capture_stream = None
            logging.info("[AUDIO_CAPTURE] Захоплення аудіо зупинено")
        except Exception as e:
            logging.error(f"[AUDIO_CAPTURE] Помилка зупинки: {e}")

def send_audio_to_stream(audio_data: bytes):
    """Додає аудіо дані до потокового буфера"""
    global audio_buffer
    try:
        audio_buffer.put(audio_data, block=False)
        logging.info(f"[STREAM] Додано до буфера: {len(audio_data)} байт")
    except queue.Full:
        logging.warning("[STREAM] Буфер переповнений")
        pass  # Буфер переповнений, пропускаємо

def start_http_server():
    """Запускає HTTP сервер для аудіо"""
    global http_server, ngrok_process, ngrok_url
    if http_server:
        return
    
    try:
        # Використовуємо 'localhost' для IPv4 та IPv6
        server_address = ('127.0.0.1', http_server_port)
        http_server = HTTPServer(server_address, AudioStreamHandler)
        
        def run_server():
            global http_server
            try:
                http_server.serve_forever()
            except:
                pass
        
        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()
        
        logging.info(f"[HTTP_SERVER] Запущено на http://{get_local_ip()}:{http_server_port}")
        
        # Запускаємо захоплення аудіо
        if AUDIO_CAPTURE_AVAILABLE:
            # Спочатку виведемо список доступних пристроїв
            try:
                devices = sd.query_devices()
                logging.info("[AUDIO_CAPTURE] Доступні пристрої:")
                for i, device in enumerate(devices):
                    if device['max_input_channels'] > 0:
                        logging.info(f"  {i}: {device['name']} (channels={device['max_input_channels']}, hostapi={device['hostapi']})")
            except:
                pass
            start_audio_capture()
        
        # Спроба запустити ngrok для публічного доступу
        try:
            from pyngrok import ngrok, conf
            
            # Шукаємо файл з ngrok authtoken
            ngrok_token_file = os.path.join(os.path.dirname(__file__), 'ngrok_token.txt')
            
            if os.path.exists(ngrok_token_file):
                with open(ngrok_token_file, 'r') as f:
                    token = f.read().strip()
                
                if token:
                    # Встановлюємо authtoken
                    conf.get_default().auth_token = token
                    
                    # Запускаємо ngrok тунель на 127.0.0.1 (IPv4)
                    tunnel = ngrok.connect(f"127.0.0.1:{http_server_port}", "http")
                    ngrok_url = tunnel.public_url
                    ngrok_process = tunnel  # Зберігаємо тунель для закриття
                    
                    logging.info(f"[NGROK] Публічний URL: {ngrok_url}")
                else:
                    logging.info("[NGROK] Token пустий в файлі ngrok_token.txt")
            else:
                logging.info(f"[NGROK] Файл ngrok_token.txt не знайдено (шлях: {ngrok_token_file})")
                logging.info("[NGROK] Створіть файл ngrok_token.txt з вашим authtoken для публічного доступу")
                
        except ImportError:
            logging.warning("[NGROK] pyngrok не встановлено, використовується локальна мережа")
        except Exception as e:
            logging.warning(f"[NGROK] Помилка: {e}")
            import traceback
            logging.debug(traceback.format_exc())
        
    except Exception as e:
        logging.error(f"[HTTP_SERVER] Помилка запуску: {e}")

def stop_http_server():
    """Зупиняє HTTP сервер і ngrok"""
    global http_server, ngrok_process, ngrok_url
    
    # Зупиняємо ngrok тунель
    if ngrok_process:
        try:
            from pyngrok import ngrok
            ngrok.disconnect(ngrok_process.public_url)
            ngrok_process = None
            ngrok_url = None
            logging.info("[NGROK] Тунель закрито")
        except Exception as e:
            logging.debug(f"[NGROK] Помилка закриття: {e}")
            ngrok_process = None
            ngrok_url = None
    
    # Зупиняємо HTTP сервер
    if http_server:
        try:
            http_server.shutdown()
            http_server = None
            logging.info("[HTTP_SERVER] Сервер зупинено")
        except:
            pass
    
    # Зупиняємо захоплення аудіо
    stop_audio_capture()

class CloudAudioStreamer:
    """
    Клас для трансляції звуку в хмару.
    Транслює інформацію про звуки дзвінків без захоплення з мікрофона.
    """
    
    def __init__(self):
        self.is_streaming = False
        self.websocket = None
        self.server_url = None
        
    def start_streaming(self, server_url: str = None):
        """
        Починає трансляцію звуку в хмару.
        Просто підключається до сервера без захоплення з мікрофона.
        """
        if self.is_streaming:
            return
            
        try:
            self.server_url = server_url or CLOUD_SERVER_URL
            self.is_streaming = True
            
            # Запускаємо HTTP сервер для аудіо
            start_http_server()
            
            # Запускаємо WebSocket клієнт в окремому потоці
            threading.Thread(target=self.websocket_client, 
                           args=(self.server_url,), 
                           daemon=True).start()
            
            # Формуємо URL для аудіо
            if ngrok_url:
                audio_url = f"{ngrok_url}"
                playlist_url = f"{ngrok_url}/live.m3u"
                stream_url = f"{ngrok_url}/live"
            else:
                local_ip = get_local_ip()
                audio_url = f"http://{local_ip}:{http_server_port}"
                playlist_url = f"http://{local_ip}:{http_server_port}/live.m3u"
                stream_url = f"http://{local_ip}:{http_server_port}/live"
            
            logging.info("[CLOUD_AUDIO] Трансляція звуку розпочата")
            messagebox.showinfo(
                "Трансляція активна",
                f"✅ Трансляція активна!\n\n"
                f"{'🌐 Доступно в інтернеті через ngrok:' if ngrok_url else '⚠️ Локальна мережа (лише в межах WiFi):'}\n"
                f"{audio_url}\n\n"
                f"📻 Плейлист: {playlist_url}\n"
                f"🎵 Прямий MP3: {stream_url}\n\n"
                f"Тепер всі звуки дзвінків будуть транслюватися."
            )
            return True
            
        except Exception as e:
            logging.error(f"[CLOUD_AUDIO] Помилка запуску трансляції: {e}")
            self.is_streaming = False
            messagebox.showerror(
                "Помилка підключення",
                f"Не вдалося підключитися до сервера:\n{e}"
            )
            return False
    
    def stop_streaming(self):
        """
        Зупиняє трансляцію звуку.
        """
        self.is_streaming = False
        
        if self.websocket:
            try:
                asyncio.run(self.websocket.close())
            except:
                pass
        
        # Зупиняємо HTTP сервер і ngrok
        stop_http_server()
            
        logging.info("[CLOUD_AUDIO] Трансляція звуку зупинена")
    
    def send_sound_event(self, sound_file: str, event_type: str = "bell"):
        """
        Відправляє аудіо дані звукового файлу на сервер для трансляції.
        
        Args:
            sound_file: Назва або шлях до звукового файлу
            event_type: Тип події (bell, alert, etc.)
        """
        if not self.is_streaming or not self.websocket:
            return
            
        try:
            # Читаємо аудіо файл як байти
            sound_path = None
            if os.path.exists(sound_file):
                sound_path = sound_file
            else:
                # Шукаємо в різних місцях
                possible_paths = [
                    os.path.join(CONFIG_DIR, sound_file),
                    os.path.join(os.path.dirname(__file__), sound_file),
                    sound_file
                ]
                for path in possible_paths:
                    if os.path.exists(path):
                        sound_path = path
                        break
            
            if not sound_path or not os.path.exists(sound_path):
                logging.warning(f"[CLOUD_AUDIO] Файл не знайдено: {sound_file}")
                return
            
            # Читаємо файл
            with open(sound_path, 'rb') as f:
                audio_data = f.read()
            
            # Отримуємо розмір файлу
            file_size = len(audio_data)
            
            # Перевіряємо розмір файлу (WebSocket має ліміт ~64KB)
            if file_size > 50000:  # 50KB
                logging.warning(f"[CLOUD_AUDIO] Файл занадто великий ({file_size} bytes), відправляємо URL")
                # Відправляємо URL для програвання через HTTP
                # Використовуємо ngrok URL якщо він доступний, інакше локальний IP
                if ngrok_url:
                    audio_url = f"{ngrok_url}/stream?file={os.path.basename(sound_file)}"
                else:
                    local_ip = get_local_ip()
                    audio_url = f"http://{local_ip}:{http_server_port}/stream?file={os.path.basename(sound_file)}"
                message = json.dumps({
                    'type': 'audio_url',
                    'event': event_type,
                    'file': os.path.basename(sound_file),
                    'url': audio_url,
                    'timestamp': datetime.datetime.now().isoformat()
                })
            else:
                # Кодуємо в base64
                encoded_audio = base64.b64encode(audio_data).decode()
                
                # Відправляємо на сервер
                message = json.dumps({
                    'type': 'audio_stream',
                    'event': event_type,
                    'file': os.path.basename(sound_file),
                    'data': encoded_audio,
                    'timestamp': datetime.datetime.now().isoformat()
                })
            
            # Створюємо новий event loop в окремому потоці
            def send_in_thread():
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(self.websocket.send(message))
                    loop.close()
                except Exception as e:
                    logging.error(f"[CLOUD_AUDIO] Помилка відправки в потоці: {e}")
            
            threading.Thread(target=send_in_thread, daemon=True).start()
            
            logging.info(f"[CLOUD_AUDIO] Відправлено аудіо поток: {sound_file} ({len(audio_data)} bytes)")
            
        except Exception as e:
            logging.error(f"[CLOUD_AUDIO] Помилка відправки звуку: {e}")
    
    def websocket_client(self, server_url: str):
        """
        WebSocket клієнт для підключення до сервера.
        """
        async def connect():
            try:
                async with websockets.connect(server_url) as websocket:
                    self.websocket = websocket
                    logging.info("[CLOUD_AUDIO] Підключено до сервера")
                    
                    # Очікуємо поки трансляція активна
                    while self.is_streaming:
                        await asyncio.sleep(1)
                        
            except Exception as e:
                logging.error(f"[CLOUD_AUDIO] Помилка підключення: {e}")
                self.is_streaming = False
        
        # Запускаємо async функцію
        asyncio.run(connect())

class CloudAudioReceiver:
    """
    Клас для отримання звуку з хмари (для Raspberry Pi).
    """
    
    def __init__(self):
        self.is_receiving = False
        self.websocket = None
        self.audio_queue = queue.Queue()
        self.stream = None
        self.p = None
        
    def start_receiving(self, server_url: str = None):
        """
        Починає отримання звуку з хмари.
        """
        if self.is_receiving:
            return
            
        try:
            self.p = pyaudio.PyAudio()
            self.stream = self.p.open(
                format=AUDIO_FORMAT,
                channels=AUDIO_CHANNELS,
                rate=AUDIO_RATE,
                output=True,
                frames_per_buffer=AUDIO_CHUNK_SIZE
            )
            
            self.is_receiving = True
            # Запускаємо WebSocket клієнт
            threading.Thread(target=self.websocket_client, 
                           args=(server_url or CLOUD_SERVER_URL,), 
                           daemon=True).start()
            
            # Запускаємо відтворення аудіо
            threading.Thread(target=self.play_audio, daemon=True).start()
            
            logging.info("[CLOUD_AUDIO] Отримання звуку розпочато")
            return True
            
        except Exception as e:
            logging.error(f"[CLOUD_AUDIO] Помилка запуску отримання: {e}")
            return False
    
    def stop_receiving(self):
        """
        Зупиняє отримання звуку.
        """
        self.is_receiving = False
        
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
            
        if self.p:
            self.p.terminate()
            self.p = None
            
        logging.info("[CLOUD_AUDIO] Отримання звуку зупинено")
    
    def websocket_client(self, server_url: str):
        """
        WebSocket клієнт для отримання аудіо.
        """
        async def receive_audio():
            try:
                async with websockets.connect(server_url) as websocket:
                    self.websocket = websocket
                    logging.info("[CLOUD_AUDIO] Підключено до сервера для отримання")
                    
                    async for message in websocket:
                        if not self.is_receiving:
                            break
                            
                        try:
                            data = json.loads(message)
                            if data.get('type') == 'audio':
                                # Декодуємо аудіо дані
                                audio_data = base64.b64decode(data['data'])
                                self.audio_queue.put(audio_data)
                                
                        except Exception as e:
                            logging.error(f"[CLOUD_AUDIO] Помилка обробки повідомлення: {e}")
                            
            except Exception as e:
                logging.error(f"[CLOUD_AUDIO] Помилка підключення для отримання: {e}")
        
        asyncio.run(receive_audio())
    
    def play_audio(self):
        """
        Відтворює отриманий аудіо.
        """
        while self.is_receiving:
            try:
                audio_data = self.audio_queue.get(timeout=0.1)
                if self.stream:
                    self.stream.write(audio_data)
            except queue.Empty:
                continue
            except Exception as e:
                logging.error(f"[CLOUD_AUDIO] Помилка відтворення: {e}")
                break

# ----------------------- ШЛЯХИ ------------------------
# Визначення базової директорії (підтримка PyInstaller)
if hasattr(sys, '_MEIPASS'):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_DIR = os.path.join(os.getenv('APPDATA') or BASE_DIR, "CloudBell")
os.makedirs(CONFIG_DIR, exist_ok=True)

CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
LICENSE_FILE = os.path.join(CONFIG_DIR, "license.key")

# Старі файли (для міграції)
OLD_SCHEDULE_FILE = os.path.join(CONFIG_DIR, "schedule.json")
OLD_FRIDAY_FILE = os.path.join(CONFIG_DIR, "friday_schedule.json")
OLD_SOUND_SETTINGS_FILE = os.path.join(CONFIG_DIR, "sound_settings.json")

# Дефолтні звуки
DEFAULT_ALERT_SOUNDS = {
    "air_alert": "air_alert.mp3",
    "air_clear": "air_clear.mp3",
    "silence": "silence.mp3"
}
DEFAULT_LESSON_DEFAULT_SOUNDS = {
    "start": "bell_start.mp3",
    "end": "bell_end.mp3"
}

# ВАЖЛИВО: ДОДАНО ПРОПУЩЕНУ КОМУ ПЕРЕД "response_1754422782525.json"
ASSET_FILES = [
    "school_logo.png", "school_icon.ico", "tray_icon.png", "school_icon.png",
    "footer_bg.gif", "my_logo.png", "facebook_icon.png",
    "speaker.png", "muted.png", "tray_icon.ico",  # ← тут була помилка
    "response_1754422782525.json"                # ← тепер окремий елемент
] + list(DEFAULT_ALERT_SOUNDS.values()) + list(DEFAULT_LESSON_DEFAULT_SOUNDS.values())


def copy_default_assets():
    """
    Копіює файли з BASE_DIR у CONFIG_DIR якщо їх там немає.
    Логує відсутність джерела окремо, щоб було видно причину.
    """
    for fname in ASSET_FILES:
        src = os.path.join(BASE_DIR, fname)
        dst = os.path.join(CONFIG_DIR, fname)
        if os.path.exists(dst):
            continue
        if not os.path.exists(src):
            logging.warning(f"[ASSET] Файл відсутній у BASE_DIR і не може бути скопійований: {src}")
            continue
        try:
            shutil.copy(src, dst)
            logging.info(f"[ASSET] Копіювання {src} -> {dst}")
        except Exception as e:
            logging.error(f"[ASSET] Помилка копіювання {src} -> {dst}: {e}")


def ensure_region_json():
    """
    Гарантує, що файл response_1754422782525.json існує у CONFIG_DIR.
    Якщо відсутній і немає оригіналу — створює заглушку.
    """
    region_file = "response_1754422782525.json"
    dst = os.path.join(CONFIG_DIR, region_file)
    if os.path.exists(dst):
        return dst

    src = os.path.join(BASE_DIR, region_file)
    if os.path.exists(src):
        try:
            shutil.copy(src, dst)
            logging.info(f"[REGIONS] Скопійовано дерево регіонів {src} -> {dst}")
            return dst
        except Exception as e:
            logging.error(f"[REGIONS] Не вдалося скопіювати регіони: {e}")

    # Створюємо мінімальний JSON (заглушку), щоб код не падав
    logging.warning("[REGIONS] Оригінальний файл відсутній. Створюємо заглушку.")
    minimal = {
        "states": [
            {
                "regionId": 19,
                "regionName": "Полтавська область",
                "regionType": "State",
                "regionChildIds": []
            }
        ]
    }
    try:
        with open(dst, "w", encoding="utf-8") as f:
            json.dump(minimal, f, ensure_ascii=False, indent=2)
        logging.info("[REGIONS] Створено заглушку з Полтавською областю.")
    except Exception as e:
        logging.error(f"[REGIONS] Не вдалося створити заглушку: {e}")
    return dst


copy_default_assets()
ensure_region_json()


# ----------------------- КОНФІГ (ЄДИНИЙ) ------------------------
DEFAULT_CONFIG = {
    "mute_weekends": False,
    "lesson_label": "Урок",
    "region": {},
    "schedules": {
        "normal": [
            ['08:00', '08:45'], ['08:55', '09:40'],
            ['09:50', '10:35'], ['10:45', '11:30'],
            ['11:40', '12:25'], ['12:40', '13:25'],
            ['13:35', '14:20'], ['14:30', '15:15']
        ],
        "friday": [
            ['08:00', '08:35'], ['08:45', '09:20'],
            ['09:30', '10:05'], ['10:15', '10:50'],
            ['11:00', '11:35'], ['11:45', '12:20'],
            ['12:30', '13:05'], ['13:15', '13:50']
        ]
    },
    "alert_sounds": {
        "air_alert": os.path.join(CONFIG_DIR, "air_alert.mp3"),
        "air_clear": os.path.join(CONFIG_DIR, "air_clear.mp3"),
        "silence": os.path.join(CONFIG_DIR, "silence.mp3")
    },
    "lesson_sounds": {
        "defaults": {
            "start": os.path.join(CONFIG_DIR, "bell_start.mp3"),
            "end": os.path.join(CONFIG_DIR, "bell_end.mp3")
        },
        "lessons": {}
    }
}

def migrate_old_files(config):
    changed = False
    # (залишив як у тебе – без змін)
    old_files = [
        ("schedule", OLD_SCHEDULE_FILE, "schedules", "normal"),
        ("friday_schedule", OLD_FRIDAY_FILE, "schedules", "friday"),
    ]
    for label, path, sect, key in old_files:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    config[sect][key] = data
                    changed = True
                os.remove(path)
                logging.info(f"Міграція {label}.json завершена.")
            except Exception as e:
                logging.error(f"Помилка міграції {label}.json: {e}")

    if os.path.exists(OLD_SOUND_SETTINGS_FILE):
        try:
            with open(OLD_SOUND_SETTINGS_FILE, "r", encoding="utf-8") as f:
                old_sound = json.load(f)
            if "bell" in old_sound:
                config["lesson_sounds"]["defaults"]["start"] = old_sound["bell"]
                if (config["lesson_sounds"]["defaults"]["end"].endswith("bell_end.mp3")
                        and not os.path.exists(config["lesson_sounds"]["defaults"]["end"])):
                    config["lesson_sounds"]["defaults"]["end"] = old_sound["bell"]
                changed = True
            for k in ["air_alert", "air_clear", "silence"]:
                if k in old_sound:
                    config["alert_sounds"][k] = old_sound[k]
                    changed = True
            os.remove(OLD_SOUND_SETTINGS_FILE)
            logging.info("Міграція sound_settings.json завершена.")
        except Exception as e:
            logging.error(f"Помилка міграції sound_settings.json: {e}")
    return changed

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            def deep_merge(dst, src):
                for k, v in src.items():
                    if k not in dst:
                        dst[k] = v
                    elif isinstance(v, dict) and isinstance(dst[k], dict):
                        deep_merge(dst[k], v)
                return dst
            cfg = deep_merge(cfg, DEFAULT_CONFIG)
            if migrate_old_files(cfg):
                save_config(cfg)
            logging.info("Конфігурацію завантажено.")
            return cfg
        except Exception as e:
            logging.error(f"Помилка завантаження конфігурації: {e}")
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if migrate_old_files(cfg):
        save_config(cfg)
    else:
        save_config(cfg)
    logging.warning("Створено новий файл конфігурації з дефолтами.")
    return cfg

def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=4)
        logging.info("Конфіг збережено.")
    except Exception as e:
        logging.error(f"Не вдалося зберегти конфіг: {e}")

CONFIG = load_config()

# ----------------------- ІНІЦІАЛІЗАЦІЯ PYGAME ------------------------
try:
    pygame.mixer.init()
except Exception as e:
    logging.error(f"Не вдалося ініціалізувати звукову систему: {e}")

# ----------------------- КЛАС ДОДАТКА -------------------------------
class CloudBellApp:
    """
    Основний клас застосунку CloudBell App.

    Ця версія включає:
      - Єдину конфігурацію (CONFIG) з динамічними розкладами та звуками.
      - Пер-урокові (start/end) звуки + дефолтні.
      - Вікно налаштувань з 3 вкладками (розклад / звуки / загальні).
      - Трирівневий вибір регіону (область → район → громада).
      - Індексація регіонів з parent-зв’язками і спадкування тривоги (громада успадковує тривогу району / області).
      - Компактний блок статусу тривоги (з індикатором), який не розтягує інтерфейс.
      - Tooltip з повним текстом назви регіону.
      - Повне кольорове оновлення блоку (без залишків зеленого при тривозі).
    """

    REGION_TREE_FILE = "response_1754422782525.json"

    # Налаштування блоку статусу регіону
    _REGION_STATUS_WIDTH = 420
    _REGION_STATUS_MAX_CHARS = 60
    _REGION_STATUS_FONT = ('Helvetica', 10, 'bold')

    def __init__(self, master: tk.Tk):
        self.master = master
        master.title("CloudBell App v. 2.1 (29.08.2025)")
        master.geometry("1200x870")
        master.configure(bg=COLORS['background'])
        master.minsize(1000, 750)
        
        # Перевірка ліцензії
        self.license_valid, self.license_org, self.license_email = self.check_license()
        if not self.license_valid:
            self.show_license_dialog()
            return

        # Іконка
        try:
            master.iconbitmap(os.path.join(CONFIG_DIR, 'school_icon.ico'))
        except Exception:
            try:
                icon = Image.open(os.path.join(CONFIG_DIR, "school_icon.png"))
                master.iconphoto(False, ImageTk.PhotoImage(icon))
            except Exception as e:
                logging.warning(f"Іконка не встановлена: {e}")

        # --- Стан ---
        self.last_special_day = None
        self.current_volume = 0.5
        self.last_bell_played = None
        self.muted = False
        self.mute_weekends = CONFIG.get("mute_weekends", False)
        self.lesson_label = CONFIG.get("lesson_label", "Урок")
        self.air_alarm_active = False

        # --- Розклади ---
        self.normal_schedule = CONFIG["schedules"]["normal"]
        self.friday_schedule = CONFIG["schedules"]["friday"]
        self.is_friday_schedule = (datetime.datetime.today().weekday() == 4)

        # --- Звуки ---
        self.alert_sounds_cfg = CONFIG["alert_sounds"]
        self.lesson_sounds_cfg = CONFIG["lesson_sounds"]
        self.air_alert_sound = None
        self.air_clear_sound = None
        self.load_air_sounds()

        # --- Регіони ---
        self.region_tree = self.load_region_tree()
        self.region_index = {}
        self.region_parent = {}
        self._index_region_tree(self.region_tree)  # індексація + parent
        self.selected_oblast = tk.StringVar()
        self.selected_rayon = tk.StringVar()
        self.selected_community = tk.StringVar()
        self.selected_region_id = tk.StringVar()
        self.region_config = CONFIG.get("region", {})
        self.init_region_selection_vars()

        # --- Активні тривоги (множина regionId рядків) ---
        self._active_alert_ids = set()
        
        # --- Хмарна трансляція ---
        self.cloud_streamer = CloudAudioStreamer()
        self.cloud_receiver = CloudAudioReceiver()
        self.cloud_enabled = False

        # --- GUI ---
        self.setup_styles()
        self.load_assets()
        self.create_gui()
        self.create_footer()

        # Канал для тривоги
        self.air_alarm_channel = pygame.mixer.Channel(1)

        # Сервіси
        self.start_services()

        # Закриття
        self.master.protocol("WM_DELETE_WINDOW", self.on_close)
        logging.info("Ініціалізація завершена.")

    # ==================== ЛІЦЕНЗУВАННЯ ====================
    def check_license(self) -> tuple[bool, str, str]:
        """
        Перевіряє чи є дійсна ліцензія.
        """
        try:
            if os.path.exists(LICENSE_FILE):
                with open(LICENSE_FILE, 'r', encoding='utf-8') as f:
                    license_data = json.load(f)
                    key = license_data.get('key', '')
                    org = license_data.get('organization', '')
                    email = license_data.get('email', '')
                    
                    # Проста перевірка формату ключа
                    if key.startswith('CB-') and len(key) == 35:
                        return True, org, email
            return False, "", ""
        except Exception:
            return False, "", ""
    
    def show_license_dialog(self):
        """
        Показує діалог введення ліцензійного ключа.
        """
        dialog = tk.Toplevel(self.master)
        dialog.title("Активація CloudBell App")
        dialog.geometry("500x400")
        dialog.configure(bg=COLORS['background'])
        dialog.transient(self.master)
        dialog.grab_set()
        
        # Центрування вікна
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (500 // 2)
        y = (dialog.winfo_screenheight() // 2) - (400 // 2)
        dialog.geometry(f"500x400+{x}+{y}")
        
        # Заголовок
        title_frame = ttk.Frame(dialog)
        title_frame.pack(fill='x', padx=20, pady=20)
        
        ttk.Label(title_frame, text="🔐 Активація CloudBell App", 
                 font=('Segoe UI', 18, 'bold'), 
                 foreground=COLORS['primary']).pack()
        
        ttk.Label(title_frame, text="Введіть ліцензійний ключ для активації програми", 
                 font=('Segoe UI', 10), 
                 foreground=COLORS['secondary']).pack(pady=(5, 0))
        
        # Форма введення
        form_frame = ttk.Frame(dialog)
        form_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        ttk.Label(form_frame, text="Назва організації:", font=('Segoe UI', 10, 'bold')).pack(anchor='w', pady=(0, 5))
        org_entry = ttk.Entry(form_frame, width=50, font=('Segoe UI', 10))
        org_entry.pack(fill='x', pady=(0, 15))
        
        ttk.Label(form_frame, text="Email:", font=('Segoe UI', 10, 'bold')).pack(anchor='w', pady=(0, 5))
        email_entry = ttk.Entry(form_frame, width=50, font=('Segoe UI', 10))
        email_entry.pack(fill='x', pady=(0, 15))
        
        ttk.Label(form_frame, text="Ліцензійний ключ:", font=('Segoe UI', 10, 'bold')).pack(anchor='w', pady=(0, 5))
        key_entry = ttk.Entry(form_frame, width=50, font=('Segoe UI', 10))
        key_entry.pack(fill='x', pady=(0, 20))
        
        # Кнопки
        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill='x', padx=20, pady=20)
        
        def activate_license():
            org = org_entry.get().strip()
            email = email_entry.get().strip()
            key = key_entry.get().strip()
            
            if not org or not email or not key:
                messagebox.showerror("Помилка", "Заповніть всі поля!")
                return
            
            if not key.startswith('CB-'):
                messagebox.showerror("Помилка", "Невірний формат ключа! Ключ повинен починатися з 'CB-'")
                return
            
            # Зберігаємо інформацію про ліцензію
            save_license_info(key, org, email)
            
            messagebox.showinfo("Успіх", f"Ліцензія активована для організації: {org}")
            dialog.destroy()
            
            # Перезапускаємо програму
            self.master.after(100, self.restart_app)
        
        def generate_demo_key():
            """Генерує демо ключ для тестування"""
            demo_key = generate_license_key("Демо Організація", "demo@example.com")
            key_entry.delete(0, tk.END)
            key_entry.insert(0, demo_key)
            org_entry.delete(0, tk.END)
            org_entry.insert(0, "Демо Організація")
            email_entry.delete(0, tk.END)
            email_entry.insert(0, "demo@example.com")
        
        ttk.Button(button_frame, text="Активувати", 
                  command=activate_license, 
                  style='primary.TButton').pack(side='left', padx=(0, 10))
        
        ttk.Button(button_frame, text="Демо ключ", 
                  command=generate_demo_key, 
                  style='success.TButton').pack(side='left', padx=(0, 10))
        
        ttk.Button(button_frame, text="Вихід", 
                  command=self.master.quit, 
                  style='alert.TButton').pack(side='right')
        
        # Фокус на першому полі
        org_entry.focus()
    
    def restart_app(self):
        """Перезапускає програму після активації ліцензії"""
        self.master.destroy()
        # Запускаємо новий екземпляр
        import subprocess
        subprocess.Popen([sys.executable, __file__])

    # ==================== РЕГІОНИ ====================
    def load_region_tree(self):
        """
        Завантажує JSON структуру регіонів (очікує ключ states).
        """
        path = os.path.join(CONFIG_DIR, self.REGION_TREE_FILE)
        if not os.path.exists(path):
            logging.warning("Файл ієрархії регіонів відсутній.")
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            states = data.get("states", [])
            logging.info(f"Завантажено регіонів верхнього рівня (State): {len(states)}")
            return states
        except Exception as e:
            logging.error(f"Помилка читання регіонів: {e}")
            return []

    def _index_region_tree(self, roots):
        """
        Індекс: regionId -> node та regionId -> parentId
        Підтримуються ключі: regionChildIds / children / childRegions (лише якщо список об'єктів).
        """
        self.region_index = {}
        self.region_parent = {}

        def walk(node, parent_id):
            rid = node.get('regionId')
            if rid is not None:
                rid_str = str(rid)
                self.region_index[rid_str] = node
                self.region_parent[rid_str] = parent_id
            for k in ("regionChildIds", "children", "childRegions"):
                childs = node.get(k)
                if isinstance(childs, list) and childs and isinstance(childs[0], dict):
                    for c in childs:
                        walk(c, str(rid) if rid is not None else None)

        for root in roots:
            if isinstance(root, dict):
                walk(root, None)

        logging.debug(f"[REGION] Проіндексовано вузлів: {len(self.region_index)}")

    def init_region_selection_vars(self):
        """
        Заповнює tk.StringVar значеннями з CONFIG (і відновлює selected_region_id найглибшим).
        При відсутності назв може (теоретично) відновити їх з індексу.
        """
        rc = self.region_config
        # Автовідновлення імен за ID (якщо потрібно)
        def fill_name(id_key, name_key):
            if rc.get(id_key) and not rc.get(name_key):
                node = self.region_index.get(str(rc[id_key]))
                if node:
                    rc[name_key] = node.get("regionName", "")
        fill_name("oblast_id", "oblast_name")
        fill_name("rayon_id", "rayon_name")
        fill_name("community_id", "community_name")

        self.selected_oblast.set(rc.get("oblast_name", ""))
        self.selected_rayon.set(rc.get("rayon_name", ""))
        self.selected_community.set(rc.get("community_name", ""))

        for key in ("community_id", "rayon_id", "oblast_id"):
            if rc.get(key):
                self.selected_region_id.set(str(rc[key]))
                break

    def create_region_selection(self, parent):
        frame = ttk.LabelFrame(parent, text="Обрати регіон", padding=10)
        frame.pack(fill='x', pady=5)

        # Області
        self.oblast_name_to_obj = {}
        oblast_names = []
        for st in self.region_tree:
            if st.get('regionType') == 'State':
                name = st.get('regionName')
                if name:
                    oblast_names.append(name)
                    self.oblast_name_to_obj[name] = st
        oblast_names.sort()

        self.oblast_cb = ttk.Combobox(frame, state="readonly",
                                      values=oblast_names, textvariable=self.selected_oblast)
        self.oblast_cb.pack(fill='x', pady=2)
        self.oblast_cb.bind("<<ComboboxSelected>>", self.on_oblast_selected)

        self.rayon_cb = ttk.Combobox(frame, state="readonly", textvariable=self.selected_rayon)
        self.rayon_cb.pack(fill='x', pady=2)
        self.rayon_cb.bind("<<ComboboxSelected>>", self.on_rayon_selected)

        self.community_cb = ttk.Combobox(frame, state="readonly", textvariable=self.selected_community)
        self.community_cb.pack(fill='x', pady=2)
        self.community_cb.bind("<<ComboboxSelected>>", self.on_community_selected)

        if self.selected_oblast.get():
            self.populate_rayons()
            if self.selected_rayon.get():
                self.populate_communities()

    def on_oblast_selected(self, event=None):
        self.selected_rayon.set('')
        self.selected_community.set('')
        self.populate_rayons()
        self.save_region_config()
        self._refresh_region_alert_display()

    def on_rayon_selected(self, event=None):
        self.selected_community.set('')
        self.populate_communities()
        self.save_region_config()
        self._refresh_region_alert_display()

    def on_community_selected(self, event=None):
        self.save_region_config()
        self._refresh_region_alert_display()

    def populate_rayons(self):
        self.rayon_cb['values'] = ()
        self.rayon_name_to_obj = {}
        oblast_obj = self.oblast_name_to_obj.get(self.selected_oblast.get())
        if not oblast_obj:
            return
        rayons = oblast_obj.get("regionChildIds", [])
        rayon_names = []
        for r in rayons:
            if not isinstance(r, dict):
                continue
            nm = r.get('regionName')
            if nm:
                self.rayon_name_to_obj[nm] = r
                if r.get('regionType') == 'District':
                    rayon_names.append(nm)
        rayon_names.sort()
        self.rayon_cb['values'] = rayon_names
        if self.selected_rayon.get() not in rayon_names:
            self.selected_rayon.set('')
        if not rayon_names:
            self.selected_region_id.set(str(oblast_obj.get("regionId", "")))

    def populate_communities(self):
        self.community_cb['values'] = ()
        self.community_name_to_obj = {}
        rayon_obj = self.rayon_name_to_obj.get(self.selected_rayon.get())
        if not rayon_obj:
            oblast_obj = self.oblast_name_to_obj.get(self.selected_oblast.get())
            if oblast_obj:
                self.selected_region_id.set(str(oblast_obj.get('regionId', '')))
            return
        comms = rayon_obj.get("regionChildIds", [])
        comm_names = []
        for c in comms:
            if not isinstance(c, dict):
                continue
            nm = c.get('regionName')
            if nm:
                self.community_name_to_obj[nm] = c
                if c.get('regionType') == 'Community':
                    comm_names.append(nm)
        comm_names.sort()
        self.community_cb['values'] = comm_names
        if self.selected_community.get() not in comm_names:
            self.selected_community.set('')
        if not comm_names:
            self.selected_region_id.set(str(rayon_obj.get("regionId", "")))

    def save_region_config(self):
        oblast_obj = self.oblast_name_to_obj.get(self.selected_oblast.get(), {})
        rayon_obj = getattr(self, "rayon_name_to_obj", {}).get(self.selected_rayon.get(), {})
        community_obj = getattr(self, "community_name_to_obj", {}).get(self.selected_community.get(), {})

        region_cfg = {
            "oblast_id": str(oblast_obj.get("regionId", "")) if oblast_obj else "",
            "oblast_name": oblast_obj.get("regionName", "") if oblast_obj else "",
            "rayon_id": str(rayon_obj.get("regionId", "")) if rayon_obj else "",
            "rayon_name": rayon_obj.get("regionName", "") if rayon_obj else "",
            "community_id": str(community_obj.get("regionId", "")) if community_obj else "",
            "community_name": community_obj.get("regionName", "") if community_obj else ""
        }
        if region_cfg["community_id"]:
            self.selected_region_id.set(region_cfg["community_id"])
        elif region_cfg["rayon_id"]:
            self.selected_region_id.set(region_cfg["rayon_id"])
        else:
            self.selected_region_id.set(region_cfg["oblast_id"])

        CONFIG["region"] = region_cfg
        save_config(CONFIG)
        logging.info(f"[REGION] Оновлено вибір: {region_cfg}")

    def is_region_alert_active(self, rid: str) -> bool:
        """
        Перевіряє чи є тривога для rid або будь-якого предка.
        """
        if not rid:
            return False
        cur = rid
        visited = set()
        while cur and cur not in visited:
            if cur in self._active_alert_ids:
                return True
            visited.add(cur)
            cur = self.region_parent.get(cur)
        return False

    # ==================== ЗВУКИ / ПОДІЇ ====================
    def load_air_sounds(self):
        try:
            self.air_alert_sound = pygame.mixer.Sound(self.alert_sounds_cfg["air_alert"])
        except Exception as e:
            logging.error(f"[SOUND] air_alert не завантажено: {e}")
            self.air_alert_sound = None
        try:
            self.air_clear_sound = pygame.mixer.Sound(self.alert_sounds_cfg["air_clear"])
        except Exception as e:
            logging.error(f"[SOUND] air_clear не завантажено: {e}")
            self.air_clear_sound = None

    def get_lesson_sound_path(self, lesson_index: int, event_type: str) -> str:
        lesson_key = str(lesson_index)
        custom = self.lesson_sounds_cfg["lessons"].get(lesson_key, {})
        return custom.get(event_type) or self.lesson_sounds_cfg["defaults"][event_type]

    def play_lesson_sound(self, lesson_index: int, event_type: str):
        if self.mute_weekends and datetime.datetime.today().weekday() >= 5:
            logging.info("Вихідні — дзвінок проігноровано.")
            return
        path = self.get_lesson_sound_path(lesson_index, event_type)
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(0 if self.muted else self.current_volume)
            pygame.mixer.music.play()
            logging.info(f"[LESSON_SOUND] {event_type} урок {lesson_index}: {path}")
            
            # Транслюємо звук в хмару якщо трансляція активна
            if self.cloud_streamer.is_streaming:
                # Передаємо повний шлях до файлу
                self.cloud_streamer.send_sound_event(path, event_type)
                
        except Exception as e:
            logging.error(f"[LESSON_SOUND] Не вдалося відтворити ({lesson_index}, {event_type}): {e}")

    def play_special_event(self):
        if self.mute_weekends and datetime.datetime.today().weekday() >= 5:
            return
        try:
            path = self.alert_sounds_cfg["silence"]
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(0 if self.muted else self.current_volume)
            pygame.mixer.music.play()
            logging.info("[SPECIAL] Хвилина мовчання відтворена.")
            
            # Транслюємо звук в хмару
            if self.cloud_streamer.is_streaming:
                # Передаємо повний шлях до файлу
                self.cloud_streamer.send_sound_event(path, "silence")
                
        except Exception as e:
            logging.error(f"[SPECIAL] Не вдалося відтворити: {e}")

    # ==================== GUI / СТИЛІ ====================
    def setup_styles(self):
        self.style = ttk.Style()
        try:
            self.style.theme_use('clam')
        except Exception:
            pass
        
        # Основні стилі
        self.style.configure('.', background=COLORS['background'], foreground=COLORS['text'])
        self.style.configure('TFrame', background=COLORS['background'])
        self.style.configure('TLabel', background=COLORS['background'], foreground=COLORS['text'])
        
        # Заголовки з сучасним шрифтом
        self.style.configure('Header.TLabel', 
                           font=('Segoe UI', 14, 'bold'), 
                           foreground=COLORS['primary'])
        
        # Кнопки з новим дизайном
        self.style.configure('TButton', 
                           padding=(8, 6), 
                           font=('Segoe UI', 9),
                           relief='flat')
        self.style.configure('primary.TButton', 
                           background=COLORS['accent'], 
                           foreground='white',
                           font=('Segoe UI', 9, 'bold'))
        self.style.configure('alert.TButton', 
                           background=COLORS['alert'], 
                           foreground='white',
                           font=('Segoe UI', 9, 'bold'))
        self.style.configure('success.TButton', 
                           background=COLORS['success'], 
                           foreground='white',
                           font=('Segoe UI', 9, 'bold'))
        
        # Стилі для LabelFrame
        self.style.configure('TLabelframe', 
                           background=COLORS['card_bg'],
                           borderwidth=1,
                           relief='solid')
        self.style.configure('TLabelframe.Label', 
                           background=COLORS['card_bg'],
                           foreground=COLORS['primary'],
                           font=('Segoe UI', 11, 'bold'))
        
        # Стилі для Entry
        self.style.configure('TEntry', 
                           fieldbackground=COLORS['card_bg'],
                           borderwidth=1,
                           relief='solid',
                           font=('Segoe UI', 10))
        
        # Стилі для Combobox
        self.style.configure('TCombobox', 
                           fieldbackground=COLORS['card_bg'],
                           borderwidth=1,
                           relief='solid',
                           font=('Segoe UI', 10))

    def load_assets(self):
        logo_path = os.path.join(CONFIG_DIR, "school_logo.png")
        self.logo_img = None
        if os.path.exists(logo_path):
            try:
                img = Image.open(logo_path).resize((200, 350), Image.Resampling.LANCZOS)
                self.logo_img = ImageTk.PhotoImage(img)
            except Exception as e:
                logging.error(f"[ASSET] Логотип не завантажено: {e}")

    def create_gui(self):
        main = ttk.Frame(self.master)
        main.pack(fill='both', expand=True, padx=10, pady=10)

        # Ліва колонка
        left = ttk.Frame(main)
        left.grid(row=0, column=0, sticky='ns', padx=5)
        if self.logo_img:
            self.logo_label = ttk.Label(left, image=self.logo_img)
        else:
            self.logo_label = ttk.Label(left, text="(Логотип відсутній)")
        self.logo_label.pack(pady=5)

        ttk.Button(left, text="Оберіть логотип закладу", command=self.select_custom_logo).pack(pady=5)
        self.lbl_day_info = ttk.Label(left, style='Header.TLabel', anchor='center', justify='center')
        self.lbl_day_info.pack(pady=5, fill='x')

        # Центральна зона
        center = ttk.Frame(main)
        center.grid(row=0, column=1, sticky='nsew', padx=5)
        self.create_schedule_section(center)

        # Права колонка
        right = ttk.Frame(main)
        right.grid(row=0, column=2, sticky='nsew', padx=5)
        self.create_time_section(right)
        self.create_alerts_section(right)
        self.create_region_selection(right)
        self.create_region_status_label(right)  # новий блок статусу
        self.create_license_info(right)  # інформація про ліцензію
        self.create_cloud_audio_control(right)  # управління хмарною трансляцією
        self.create_volume_control(right)
        self.create_controls(main)

        main.columnconfigure(1, weight=1)

    def create_footer(self):
        footer_canvas = tk.Canvas(self.master, height=60, highlightthickness=0, bg="#2C3E50")
        footer_canvas.pack(side='bottom', fill='x')
        gif_path = os.path.join(CONFIG_DIR, "footer_bg.gif")
        self.gif_frames = []
        try:
            if os.path.exists(gif_path):
                with Image.open(gif_path) as img:
                    for fr in range(img.n_frames):
                        img.seek(fr)
                        frame = img.copy().resize((1200, 60), Image.Resampling.LANCZOS)
                        self.gif_frames.append(ImageTk.PhotoImage(frame))
            if self.gif_frames:
                self.current_gif_frame = 0
                self.footer_bg = footer_canvas.create_image(0, 0, anchor="nw", image=self.gif_frames[0])

                def animate():
                    if self.gif_frames:
                        self.current_gif_frame = (self.current_gif_frame + 1) % len(self.gif_frames)
                        footer_canvas.itemconfig(self.footer_bg, image=self.gif_frames[self.current_gif_frame])
                        self.master.after(60, animate)

                self.master.after(120, animate)
        except Exception as e:
            logging.error(f"[FOOTER] GIF не завантажено: {e}")

        content = tk.Frame(footer_canvas, bg="#2C3E50")
        footer_canvas.create_window(600, 23, window=content, anchor="center")

        # Лого в футері
        try:
            logo_path = os.path.join(CONFIG_DIR, "my_logo.png")
            if os.path.exists(logo_path):
                logo = Image.open(logo_path).resize((65, 40), Image.Resampling.LANCZOS)
                self.footer_logo = ImageTk.PhotoImage(logo)
                tk.Label(content, image=self.footer_logo, bg="#2C3E50").pack(side="left", padx=10)
        except Exception as e:
            logging.error(f"[FOOTER] Лого: {e}")

        def open_web(_):
            webbrowser.open("https://sydorenko.ptu44.com/")

        link = tk.Label(content, text="https://sydorenko.ptu44.com/", fg="white",
                        bg="#2C3E50", cursor="hand2", font=("Helvetica", 10, "underline"))
        link.pack(side="left", padx=10)
        link.bind("<Button-1>", open_web)

        tk.Label(content, text="Serhii Sydorenko 2025", fg="white", bg="#2C3E50").pack(side="left", padx=10)

        fb_path = os.path.join(CONFIG_DIR, "facebook_icon.png")
        try:
            if os.path.exists(fb_path):
                fb_icon = Image.open(fb_path).resize((32, 32), Image.Resampling.LANCZOS)
                self.fb_icon_img = ImageTk.PhotoImage(fb_icon)
                tk.Button(content, image=self.fb_icon_img,
                          command=lambda: webbrowser.open("https://www.facebook.com/sergey.sydorenk0/"),
                          bg="#2C3E50", activebackground="#2C3E50",
                          borderwidth=0).pack(side="right", padx=10)
        except Exception as e:
            logging.error(f"[FOOTER] FB icon: {e}")

    # -------- Секції центру / правої колонки --------
    def create_schedule_section(self, parent):
        frame = ttk.LabelFrame(parent, text="Активний розклад", padding=5)
        frame.pack(fill='both', expand=True)
        self.lbl_schedule_type = ttk.Label(frame, style='Header.TLabel', foreground=COLORS['primary'])
        self.lbl_schedule_type.pack()
        self.schedule_table = ttk.Frame(frame)
        self.schedule_table.pack(pady=3)
        self.update_schedule_display()

        btns_wrap = ttk.Frame(frame)
        btns_wrap.pack(side="bottom", fill="x", pady=3)

        btns = ttk.Frame(btns_wrap)
        btns.pack()  # без fill, автоматично по центру (можна anchor='center')

        ttk.Button(btns, text="⚙️ Розклад / Звуки уроків",
                   command=self.open_schedule_settings,
                   style='primary.TButton').pack(side='left', padx=3)

        ttk.Button(btns, text="🔔 Звуки тривог",
                   command=self.open_alert_sound_settings,
                   style='primary.TButton').pack(side='left', padx=3)

    def update_schedule_display(self):
        for w in self.schedule_table.winfo_children():
            w.destroy()
        schedule = self.get_current_schedule()
        schedule_type = "РОЗКЛАД П'ЯТНИЦІ" if self.is_friday_schedule else "ЗВИЧАЙНИЙ РОЗКЛАД"
        self.lbl_schedule_type.config(text=schedule_type)
        ttk.Label(self.schedule_table, text=self.lesson_label, style='Header.TLabel').grid(row=0, column=0, padx=10)
        ttk.Label(self.schedule_table, text="Початок", style='Header.TLabel').grid(row=0, column=1, padx=10)
        ttk.Label(self.schedule_table, text="Кінець", style='Header.TLabel').grid(row=0, column=2, padx=10)
        for idx, (start, end) in enumerate(schedule, start=1):
            ttk.Label(self.schedule_table, text=str(idx)).grid(row=idx, column=0)
            ttk.Label(self.schedule_table, text=start).grid(row=idx, column=1)
            ttk.Label(self.schedule_table, text=end).grid(row=idx, column=2)

    def create_time_section(self, parent):
        frame = ttk.LabelFrame(parent, text="Час та статус", padding=5)
        frame.pack(fill='x', pady=2)
        self.lbl_current_time = ttk.Label(frame, font=('Segoe UI', 20, 'bold'), foreground=COLORS['primary'])
        self.lbl_current_time.pack()
        self.lbl_lesson_status = ttk.Label(frame, font=('Segoe UI', 9), foreground=COLORS['secondary'])
        self.lbl_lesson_status.pack()
        self.lbl_special_event = ttk.Label(frame, text="До хвилини мовчання: --:--",
                                           font=('Segoe UI', 9), foreground=COLORS['secondary'])
        self.lbl_special_event.pack(pady=2)

    def create_alerts_section(self, parent):
        frame = ttk.LabelFrame(parent, text="Активні тривоги", padding=5)
        frame.pack(fill='both', expand=True, pady=2)
        self.alert_listbox = tk.Listbox(
            frame, height=5, width=35,
            bg=COLORS['card_bg'], fg=COLORS['text'],
            font=('Segoe UI', 8),
            selectbackground=COLORS['accent'],
            relief='flat',
            borderwidth=1
        )
        scrollbar = ttk.Scrollbar(frame, command=self.alert_listbox.yview)
        self.alert_listbox.config(yscrollcommand=scrollbar.set)
        self.alert_listbox.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

    # ====== НОВИЙ БЛОК СТАТУСУ РЕГІОНУ (Canvas, фіксована ширина) ======
    def create_region_status_label(self, parent):
        """
        Створює фіксований за розміром (у пікселях) блок статусу регіону на Canvas.
        Головне вікно більше не перераховує ширину при зміні тексту.
        """
        # Налаштування (можете підкрутити ширину / висоту)
        self._region_bar_width = 350
        self._region_bar_height = 36
        self._region_bar_padding_left = 34  # зсув тексту після індикатора
        self._region_bar_font = tkfont.Font(family="Segoe UI", size=9, weight="bold")
        self._region_bar_font_color = "#FFFFFF"
        self._region_bar_bg_ok = COLORS['success']
        self._region_bar_bg_alert = COLORS['alert']
        self._region_bar_dot_ok = "#A7F3D0"
        self._region_bar_dot_alert = "#FFFFFF"
        self._region_bar_dot_radius = 7

        # Контейнер фіксованого розміру
        wrapper = tk.Frame(parent,
                           width=self._region_bar_width,
                           height=self._region_bar_height,
                           bg=COLORS['background'])
        wrapper.pack(pady=2)
        wrapper.pack_propagate(False)
        self._region_status_wrapper = wrapper

        # Canvas
        cv = tk.Canvas(wrapper,
                       width=self._region_bar_width,
                       height=self._region_bar_height,
                       bd=0,
                       highlightthickness=0,
                       bg=COLORS['background'])
        cv.pack(fill='both', expand=True)
        self._region_status_canvas = cv

        # Прямокутник фон
        self._region_status_rect = cv.create_rectangle(
            0, 0, self._region_bar_width, self._region_bar_height,
            outline=self._region_bar_bg_ok, fill=self._region_bar_bg_ok
        )

        # Коло-індикатор
        r = self._region_bar_dot_radius
        cy = self._region_bar_height // 2
        cx = 14
        self._region_status_dot = cv.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            outline="", fill=self._region_bar_dot_ok
        )

        # Текст (тимчасово)
        initial_text = "Регіон не вибрано: Тривоги немає"
        self._region_status_text_id = cv.create_text(
            self._region_bar_padding_left,
            cy,
            anchor='w',
            text=initial_text,
            font=self._region_bar_font,
            fill=self._region_bar_font_color
        )

        self._region_status_full_text = initial_text
        self._region_status_current_alert = False

        # Tooltip
        self._region_status_tooltip = self._RegionStatusTooltip(cv, initial_text)

        # Marquee (опціонально)
        self._region_marquee_job = None
        self._region_marquee_offset = 0
        cv.bind("<Enter>", self._region_bar_on_enter)
        cv.bind("<Leave>", self._region_bar_on_leave)

    def _region_bar_on_enter(self, _):
        # Якщо хочете, щоб довгий текст “scroll” при наведенні — розкоментуйте наступний рядок:
        # self._start_region_marquee()
        pass

    def _region_bar_on_leave(self, _):
        # Зупинка marquee
        if self._region_marquee_job:
            try:
                self._region_status_canvas.after_cancel(self._region_marquee_job)
            except Exception:
                pass
            self._region_marquee_job = None
            self._region_marquee_offset = 0
            # Перемалювати обрізаний текст
            self._render_region_status_text(self._region_status_full_text, self._region_status_current_alert)

    def _start_region_marquee(self):
        """
        Простий marquee (бігучий рядок) для дуже довгих текстів. Викликається тільки
        якщо ви явно розкоментували у _region_bar_on_enter.
        """
        text = self._region_status_full_text
        cv = self._region_status_canvas
        full_px = self._region_bar_font.measure(text)
        avail = self._region_bar_width - self._region_bar_padding_left - 10
        if full_px <= avail:
            return  # не потрібно

        def step():
            if self._region_marquee_job is None:
                return
            self._region_marquee_offset += 2
            total_span = full_px + 40
            if self._region_marquee_offset > total_span:
                self._region_marquee_offset = 0
            cv.delete(self._region_status_text_id)
            self._region_status_text_id = cv.create_text(
                self._region_bar_padding_left - self._region_marquee_offset,
                self._region_bar_height // 2,
                anchor='w',
                text=text,
                font=self._region_bar_font,
                fill=self._region_bar_font_color
            )
            self._region_marquee_job = cv.after(50, step)

        if not self._region_marquee_job:
            self._region_marquee_job = cv.after(60, step)

    def _render_region_status_text(self, full_text: str, is_alert: bool):
        """
        Малює (або перемальовує) текст у Canvas з обрізанням по фактичній ширині.
        """
        cv = self._region_status_canvas
        try:
            cv.delete(self._region_status_text_id)
        except Exception:
            pass

        avail = self._region_bar_width - self._region_bar_padding_left - 10
        if self._region_bar_font.measure(full_text) <= avail:
            display = full_text
        else:
            base = full_text
            ell = "…"
            # Прямий зворотній цикл (можна оптимізувати бінарним пошуком — тут не критично)
            for cut in range(len(base), 0, -1):
                candidate = base[:cut] + ell
                if self._region_bar_font.measure(candidate) <= avail:
                    display = candidate
                    break
            else:
                display = ell

        self._region_status_text_id = cv.create_text(
            self._region_bar_padding_left,
            self._region_bar_height // 2,
            anchor='w',
            text=display,
            font=self._region_bar_font,
            fill=self._region_bar_font_color
        )

    def update_region_status(self, status: bool, manual=False):
        """
        Замінює попередній метод. Викликайте так само.
        Повністю фіксована ширина – вікно не змінює розмір.
        """
        if self.mute_weekends and datetime.datetime.today().weekday() >= 5 and not manual:
            return

        region_name = (self.selected_community.get()
                       or self.selected_rayon.get()
                       or self.selected_oblast.get()
                       or "Регіон не вибрано")
        full_text = f"{region_name}: {'ТРИВОГА!' if status else 'Тривоги немає'}"

        self._region_status_full_text = full_text
        self._region_status_current_alert = status

        cv = self._region_status_canvas
        bg = self._region_bar_bg_alert if status else self._region_bar_bg_ok
        dot = self._region_bar_dot_alert if status else self._region_bar_dot_ok

        cv.itemconfig(self._region_status_rect, fill=bg, outline=bg)
        cv.itemconfig(self._region_status_dot, fill=dot)

        self._render_region_status_text(full_text, status)

        if hasattr(self, "_region_status_tooltip"):
            self._region_status_tooltip.text = full_text

        if status != self.air_alarm_active:
            self.air_alarm_active = status
            snd = self.air_alert_sound if status else self.air_clear_sound
            sound_type = "air_alert" if status else "air_clear"
            if snd and not self.muted:
                try:
                    self.air_alarm_channel.play(snd)
                    
                    # Транслюємо звук тривоги в хмару
                    if self.cloud_streamer.is_streaming:
                        path = self.alert_sounds_cfg[sound_type]
                        self.cloud_streamer.send_sound_event(path, sound_type)
                        
                except Exception as e:
                    logging.error(f"[ALARM_SOUND] {e}")

    def update_poltava_status(self, status, manual=False):
        # Зворотна сумісність
        self.update_region_status(status, manual=manual)

    class _RegionStatusTooltip:
        """
        Tooltip для Canvas блоку (використовується тільки тут).
        """

        def __init__(self, widget, text="", delay=600):
            self.widget = widget
            self.text = text
            self.delay = delay
            self._after = None
            self.tw = None
            widget.bind("<Enter>", self._enter)
            widget.bind("<Leave>", self._leave)
            widget.bind("<ButtonPress>", self._leave)

        def _enter(self, _=None):
            self._cancel()
            self._after = self.widget.after(self.delay, self._show)

        def _leave(self, _=None):
            self._cancel()
            self._hide()

        def _cancel(self):
            if self._after:
                try:
                    self.widget.after_cancel(self._after)
                except Exception:
                    pass
                self._after = None

        def _show(self):
            if self.tw or not self.text:
                return
            try:
                x = self.widget.winfo_rootx() + 10
                y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
            except Exception:
                return
            self.tw = tk.Toplevel(self.widget)
            self.tw.wm_overrideredirect(True)
            self.tw.wm_geometry(f"+{x}+{y}")
            lbl = tk.Label(self.tw,
                           text=self.text,
                           bg="#333333",
                           fg="white",
                           font=("Helvetica", 9),
                           relief='solid',
                           borderwidth=1,
                           wraplength=520,
                           padx=6, pady=4)
            lbl.pack()

        def _hide(self):
            if self.tw:
                try:
                    self.tw.destroy()
                except Exception:
                    pass
                self.tw = None

    def create_license_info(self, parent):
        """
        Створює блок з інформацією про ліцензію.
        """
        frame = ttk.LabelFrame(parent, text="Ліцензія", padding=5)
        frame.pack(fill='x', pady=2)
        
        # Інформація про організацію
        org_label = ttk.Label(frame, text=f"Організація: {self.license_org}", 
                             font=('Segoe UI', 8, 'bold'),
                             foreground=COLORS['primary'])
        org_label.pack(anchor='w', pady=(0, 1))
        
        # Email
        email_label = ttk.Label(frame, text=f"Email: {self.license_email}", 
                               font=('Segoe UI', 7),
                               foreground=COLORS['secondary'])
        email_label.pack(anchor='w', pady=(0, 1))
        
        # Статус ліцензії
        status_label = ttk.Label(frame, text="✅ Ліцензія активна", 
                                font=('Segoe UI', 7),
                                foreground=COLORS['success'])
        status_label.pack(anchor='w', pady=(0, 3))
        
        # Кнопка зміни ліцензії
        ttk.Button(frame, text="Змінити ліцензію", 
                  command=self.show_license_dialog,
                  style='primary.TButton').pack(fill='x')

    def create_cloud_audio_control(self, parent):
        """
        Створює блок управління хмарною трансляцією звуку.
        """
        frame = ttk.LabelFrame(parent, text="☁️ Хмарна трансляція", padding=5)
        frame.pack(fill='x', pady=2)
        
        # Статус трансляції
        self.cloud_status_label = ttk.Label(frame, text="🔴 Трансляція вимкнена", 
                                          font=('Segoe UI', 8, 'bold'),
                                          foreground=COLORS['alert'])
        self.cloud_status_label.pack(anchor='w', pady=(0, 5))
        
        # URL сервера
        url_frame = ttk.Frame(frame)
        url_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Label(url_frame, text="Сервер:", font=('Segoe UI', 8, 'bold')).pack(anchor='w')
        self.server_url_var = tk.StringVar(value=CLOUD_SERVER_URL)
        server_entry = ttk.Entry(url_frame, textvariable=self.server_url_var, 
                               font=('Segoe UI', 8), width=40)
        server_entry.pack(fill='x', pady=(1, 0))
        
        # Кнопки управління
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill='x')
        
        self.start_stream_btn = ttk.Button(button_frame, text="▶️ Почати трансляцію", 
                                         command=self.start_cloud_streaming,
                                         style='success.TButton')
        self.start_stream_btn.pack(side='left', padx=(0, 5))
        
        self.stop_stream_btn = ttk.Button(button_frame, text="⏹️ Зупинити", 
                                        command=self.stop_cloud_streaming,
                                        style='alert.TButton',
                                        state='disabled')
        self.stop_stream_btn.pack(side='left', padx=(0, 5))
        
        # Інформація
        info_label = ttk.Label(frame, 
                              text="💡 Для публічної трансляції розгорніть сервер на Railway.app",
                              font=('Segoe UI', 7),
                              foreground=COLORS['secondary'])
        info_label.pack(anchor='w', pady=(2, 0))
        
        help_label = ttk.Label(frame, 
                              text="📖 Читайте: ШВИДКИЙ_СТАРТ.md для інструкцій",
                              font=('Segoe UI', 7),
                              foreground=COLORS['accent'],
                              cursor='hand2')
        help_label.pack(anchor='w', pady=(0, 0))
        
        def open_help(event):
            help_file = os.path.join(os.path.dirname(__file__), "ШВИДКИЙ_СТАРТ.md")
            if os.path.exists(help_file):
                os.startfile(help_file)
        
        help_label.bind('<Button-1>', open_help)

    def start_cloud_streaming(self):
        """
        Починає хмарну трансляцію звуку.
        """
        try:
            server_url = self.server_url_var.get().strip()
            if not server_url:
                messagebox.showerror("Помилка", "Введіть URL сервера!")
                return
            
            if self.cloud_streamer.start_streaming(server_url):
                self.cloud_enabled = True
                self.cloud_status_label.config(text="🟢 Трансляція активна", 
                                             foreground=COLORS['success'])
                self.start_stream_btn.config(state='disabled')
                self.stop_stream_btn.config(state='normal')
                messagebox.showinfo("Успіх", "Хмарна трансляція розпочата!")
            else:
                messagebox.showerror("Помилка", "Не вдалося розпочати трансляцію!")
                
        except Exception as e:
            messagebox.showerror("Помилка", f"Помилка запуску трансляції: {e}")
    
    def stop_cloud_streaming(self):
        """
        Зупиняє хмарну трансляцію звуку.
        """
        try:
            self.cloud_streamer.stop_streaming()
            self.cloud_enabled = False
            self.cloud_status_label.config(text="🔴 Трансляція вимкнена", 
                                         foreground=COLORS['alert'])
            self.start_stream_btn.config(state='normal')
            self.stop_stream_btn.config(state='disabled')
            messagebox.showinfo("Успіх", "Хмарна трансляція зупинена!")
            
        except Exception as e:
            messagebox.showerror("Помилка", f"Помилка зупинки трансляції: {e}")

    def create_volume_control(self, parent):
        frame = ttk.LabelFrame(parent, text="Гучність", padding=3)
        frame.pack(fill='x', pady=2)
        self.volume_scale = ttk.Scale(
            frame, from_=0.0, to=1.0, value=self.current_volume,
            command=self.set_volume
        )
        self.volume_scale.pack(fill='x')

    def create_controls(self, parent):
        btn_frame = ttk.Frame(parent)
        btn_frame.grid(row=1, column=0, columnspan=3, pady=5)

        self.friday_toggle = ttk.Button(
            btn_frame,
            text=("Перемкнути на звичайний розклад"
                  if self.is_friday_schedule else "Перемкнути на розклад п'ятниці"),
            command=self.toggle_friday_mode
        )
        self.friday_toggle.pack(side='left', padx=5)

        ttk.Button(btn_frame, text="▶ Тест (початок)",
                   command=lambda: self.play_lesson_sound(1, 'start'),
                   style='primary.TButton').pack(side='left', padx=3)
        ttk.Button(btn_frame, text="▶ Тест (кінець)",
                   command=lambda: self.play_lesson_sound(1, 'end'),
                   style='primary.TButton').pack(side='left', padx=3)
        ttk.Button(btn_frame, text="⏹ Стоп",
                   command=self.stop_music,
                   style='alert.TButton').pack(side='left', padx=3)

        # Mute
        try:
            self.mute_icon = ImageTk.PhotoImage(Image.open(os.path.join(CONFIG_DIR, "speaker.png")).resize((24, 24)))
            self.muted_icon = ImageTk.PhotoImage(Image.open(os.path.join(CONFIG_DIR, "muted.png")).resize((24, 24)))
        except Exception:
            self.mute_icon = self.muted_icon = None
        self.mute_button = ttk.Button(btn_frame, image=self.mute_icon, command=self.toggle_mute)
        self.mute_button.pack(side='left', padx=5)

        # Тести тривоги
        ttk.Button(btn_frame, text="Тест: Тривога",
                   command=lambda: self.manual_air_alarm(True),
                   style='alert.TButton').pack(side='left', padx=3)
        ttk.Button(btn_frame, text="Тест: Відбій",
                   command=lambda: self.manual_air_alarm(False),
                   style='primary.TButton').pack(side='left', padx=3)

        # Вихід
        ttk.Button(btn_frame, text="❌ Вихід",
                   command=self.master.destroy,
                   style='primary.TButton').pack(side='right', padx=3)

    # ==================== НАЛАШТУВАННЯ (РОЗКЛАД / ЗВУКИ) ====================
    def open_schedule_settings(self):
        """
        Вікно з 3 вкладками:
          - Розклад (звичайний, п'ятниця) + додати/видалити урок
          - Звуки уроків (пер-урокові + дефолти, тест програвання)
          - Загальні (lesson_label, mute_weekends)
        Збереження: Застосувати або Зберегти і закрити. Підтвердження при незбережених змінах.
        """
        if hasattr(self, "_sched_win") and self._sched_win and tk.Toplevel.winfo_exists(self._sched_win):
            self._sched_win.lift()
            self._sched_win.focus_force()
            return

        win = tk.Toplevel(self.master)
        self._sched_win = win
        win.title("Налаштування: Розклад та Звуки уроків")
        win.geometry("1000x680")
        win.minsize(920, 600)
        win.transient(self.master)
        win.grab_set()

        self._unsaved_changes = False

        def mark_changed(*_):
            self._unsaved_changes = True

        notebook = ttk.Notebook(win)
        notebook.pack(fill='both', expand=True, padx=8, pady=8)

        tab_schedule = ttk.Frame(notebook)
        tab_lesson_sounds = ttk.Frame(notebook)
        tab_general = ttk.Frame(notebook)
        notebook.add(tab_schedule, text="Розклад")
        notebook.add(tab_lesson_sounds, text="Звуки уроків")
        notebook.add(tab_general, text="Загальні")

        # ---- TAB: РОЗКЛАД ----
        sched_container = ttk.Frame(tab_schedule)
        sched_container.pack(fill='both', expand=True, pady=5)
        left_sched = ttk.LabelFrame(sched_container, text="Звичайні дні (Пн-Чт; Сб,Нд ігнор.)", padding=8)
        left_sched.grid(row=0, column=0, sticky='nsew', padx=5)
        right_sched = ttk.LabelFrame(sched_container, text="П'ятниця", padding=8)
        right_sched.grid(row=0, column=1, sticky='nsew', padx=5)
        sched_container.columnconfigure(0, weight=1)
        sched_container.columnconfigure(1, weight=1)
        sched_container.rowconfigure(0, weight=1)

        self.schedule_rows_normal = []
        self.schedule_rows_friday = []

        def build_schedule_table(container, schedule, store_list):
            headers = ("#", "Початок", "Кінець", "Копіювати")
            for c, h in enumerate(headers):
                ttk.Label(container, text=h, style='Header.TLabel').grid(row=0, column=c, padx=4, pady=3, sticky='w')
            # Очистка рядків > 0
            for w in [w for w in container.grid_slaves() if int(w.grid_info().get("row")) > 0]:
                w.destroy()
            store_list.clear()
            for idx, (start, end) in enumerate(schedule, start=1):
                ttk.Label(container, text=str(idx)).grid(row=idx, column=0, padx=4, pady=2)
                e_start = ttk.Entry(container, width=8)
                e_start.insert(0, start); e_start.grid(row=idx, column=1, padx=4, pady=2)
                e_start.bind("<KeyRelease>", mark_changed)
                e_end = ttk.Entry(container, width=8)
                e_end.insert(0, end); e_end.grid(row=idx, column=2, padx=4, pady=2)
                e_end.bind("<KeyRelease>", mark_changed)

                def copy_to_clip(s=start, e=end):
                    self.master.clipboard_clear()
                    self.master.clipboard_append(f"{s}-{e}")

                ttk.Button(container, text="⇅", width=3, command=copy_to_clip).grid(row=idx, column=3, padx=3, pady=2)
                store_list.append((e_start, e_end))

        build_schedule_table(left_sched, self.normal_schedule, self.schedule_rows_normal)
        build_schedule_table(right_sched, self.friday_schedule, self.schedule_rows_friday)

        ctrl_schedule = ttk.Frame(tab_schedule)
        ctrl_schedule.pack(fill='x', pady=6)

        def _generate_next_time(prev_str: str, add_minutes: int) -> str:
            try:
                h, m = map(int, prev_str.split(":"))
                m += add_minutes
                h += m // 60
                m %= 60
                h %= 24
                return f"{h:02}:{m:02}"
            except Exception:
                return "08:00"

        def add_lesson():
            if self.normal_schedule:
                new_start_norm = _generate_next_time(self.normal_schedule[-1][1], 10)
                new_end_norm = _generate_next_time(new_start_norm, 45)
            else:
                new_start_norm, new_end_norm = "08:00", "08:45"
            if self.friday_schedule:
                new_start_fri = _generate_next_time(self.friday_schedule[-1][1], 10)
                new_end_fri = _generate_next_time(new_start_fri, 35)
            else:
                new_start_fri, new_end_fri = "08:00", "08:35"

            self.normal_schedule.append([new_start_norm, new_end_norm])
            self.friday_schedule.append([new_start_fri, new_end_fri])
            build_schedule_table(left_sched, self.normal_schedule, self.schedule_rows_normal)
            build_schedule_table(right_sched, self.friday_schedule, self.schedule_rows_friday)
            rebuild_lesson_sound_rows()
            mark_changed()

        def remove_lesson():
            if self.normal_schedule:
                self.normal_schedule.pop()
            if self.friday_schedule:
                self.friday_schedule.pop()
            target_key = str(max(len(self.normal_schedule), len(self.friday_schedule)) + 1)
            self.lesson_sounds_cfg["lessons"].pop(target_key, None)
            build_schedule_table(left_sched, self.normal_schedule, self.schedule_rows_normal)
            build_schedule_table(right_sched, self.friday_schedule, self.schedule_rows_friday)
            rebuild_lesson_sound_rows()
            mark_changed()

        ttk.Button(ctrl_schedule, text="➕ Додати урок", command=add_lesson).pack(side='left', padx=4)
        ttk.Button(ctrl_schedule, text="➖ Видалити останній", command=remove_lesson).pack(side='left', padx=4)
        ttk.Label(ctrl_schedule, text="Всього уроків:").pack(side='left', padx=12)
        total_lessons_var = tk.StringVar(value=str(len(self.normal_schedule)))
        ttk.Label(ctrl_schedule, textvariable=total_lessons_var,
                  foreground=COLORS['primary']).pack(side='left')

        def refresh_total():
            total_lessons_var.set(str(len(self.normal_schedule)))
            ctrl_schedule.after(1200, refresh_total)
        refresh_total()

        # ---- TAB: ЗВУКИ УРОКІВ ----
        sounds_outer = ttk.Frame(tab_lesson_sounds)
        sounds_outer.pack(fill='both', expand=True)
        canvas = tk.Canvas(sounds_outer, highlightthickness=0, bg=COLORS['background'])
        vsb = ttk.Scrollbar(sounds_outer, orient="vertical", command=canvas.yview)
        hsb = ttk.Scrollbar(sounds_outer, orient="horizontal", command=canvas.xview)
        inner = ttk.Frame(canvas)
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")

        def _on_configure(_):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(inner_id, width=canvas.winfo_width())
        inner.bind("<Configure>", _on_configure)

        headers = ("#", "Start звук", "Файл (start)", "End звук", "Файл (end)", "▶", "✖")
        for c, h in enumerate(headers):
            ttk.Label(inner, text=h, style="Header.TLabel").grid(row=0, column=c, padx=4, pady=4, sticky='w')

        self.lesson_sound_rows = []

        def browse_into(entry: ttk.Entry):
            path = filedialog.askopenfilename(
                title="Оберіть аудіо (mp3/wav)",
                filetypes=[("Аудіо файли", "*.mp3 *.wav")]
            )
            if path:
                entry.delete(0, tk.END)
                entry.insert(0, path)
                mark_changed()

        def clear_entry(entry: ttk.Entry):
            entry.delete(0, tk.END)
            mark_changed()

        def play_temp(path: str):
            if not path:
                messagebox.showwarning("Увага", "Файл не вказано.")
                return
            try:
                pygame.mixer.music.load(path)
                pygame.mixer.music.set_volume(0 if self.muted else self.current_volume)
                pygame.mixer.music.play()
            except Exception as e:
                messagebox.showerror("Помилка", f"Не вдалося відтворити: {e}")

        def rebuild_lesson_sound_rows():
            for w in [w for w in inner.grid_slaves() if int(w.grid_info().get("row")) > 0]:
                w.destroy()
            self.lesson_sound_rows.clear()
            total = max(len(self.normal_schedule), len(self.friday_schedule))
            for i in range(1, total + 1):
                ttk.Label(inner, text=str(i)).grid(row=i, column=0, padx=3, pady=2, sticky='w')
                start_entry = ttk.Entry(inner, width=28)
                start_entry.insert(0, self.lesson_sounds_cfg["lessons"].get(str(i), {}).get("start", ""))
                start_entry.grid(row=i, column=2, padx=3, pady=2, sticky='w')
                start_entry.bind("<KeyRelease>", mark_changed)
                ttk.Button(inner, text="...", width=3,
                           command=lambda e=start_entry: browse_into(e)).grid(row=i, column=1, padx=3, pady=2)

                end_entry = ttk.Entry(inner, width=28)
                end_entry.insert(0, self.lesson_sounds_cfg["lessons"].get(str(i), {}).get("end", ""))
                end_entry.grid(row=i, column=4, padx=3, pady=2, sticky='w')
                end_entry.bind("<KeyRelease>", mark_changed)
                ttk.Button(inner, text="...", width=3,
                           command=lambda e=end_entry: browse_into(e)).grid(row=i, column=3, padx=3, pady=2)

                ttk.Button(inner, text="▶", width=3,
                           command=lambda se=start_entry, ee=end_entry: play_temp(se.get() or ee.get())
                           ).grid(row=i, column=5, padx=2)
                ttk.Button(inner, text="✖", width=3,
                           command=lambda se=start_entry, ee=end_entry: (clear_entry(se), clear_entry(ee))
                           ).grid(row=i, column=6, padx=2)
                self.lesson_sound_rows.append((i, start_entry, end_entry))

        rebuild_lesson_sound_rows()

        defaults_frame = ttk.LabelFrame(tab_lesson_sounds, text="Дефолтні звуки (якщо не задані окремі)", padding=8)
        defaults_frame.pack(fill='x', padx=5, pady=5)
        def_start_var = tk.StringVar(value=self.lesson_sounds_cfg["defaults"]["start"])
        def_end_var = tk.StringVar(value=self.lesson_sounds_cfg["defaults"]["end"])
        ttk.Label(defaults_frame, text="Start (деф.):").grid(row=0, column=0, sticky='w', padx=5, pady=3)
        def_start_entry = ttk.Entry(defaults_frame, textvariable=def_start_var, width=60)
        def_start_entry.grid(row=0, column=1, padx=5, pady=3); def_start_entry.bind("<KeyRelease>", mark_changed)
        ttk.Button(defaults_frame, text="Обрати",
                   command=lambda: self._browse_to_var(def_start_var, mark_changed)).grid(row=0, column=2, padx=5)
        ttk.Button(defaults_frame, text="▶", command=lambda: play_temp(def_start_var.get())).grid(row=0, column=3, padx=2)

        ttk.Label(defaults_frame, text="End (деф.):").grid(row=1, column=0, sticky='w', padx=5, pady=3)
        def_end_entry = ttk.Entry(defaults_frame, textvariable=def_end_var, width=60)
        def_end_entry.grid(row=1, column=1, padx=5, pady=3); def_end_entry.bind("<KeyRelease>", mark_changed)
        ttk.Button(defaults_frame, text="Обрати",
                   command=lambda: self._browse_to_var(def_end_var, mark_changed)).grid(row=1, column=2, padx=5)
        ttk.Button(defaults_frame, text="▶", command=lambda: play_temp(def_end_var.get())).grid(row=1, column=3, padx=2)

        # ---- TAB: ЗАГАЛЬНІ ----
        general_frame = ttk.Frame(tab_general, padding=10)
        general_frame.pack(fill='both', expand=True)
        lesson_label_var = tk.StringVar(value=self.lesson_label)
        mute_weekends_var = tk.BooleanVar(value=self.mute_weekends)
        ttk.Label(general_frame, text="Назва ітерації (Урок/Пара):").grid(row=0, column=0, sticky='w', padx=4, pady=4)
        lesson_label_entry = ttk.Entry(general_frame, textvariable=lesson_label_var, width=20)
        lesson_label_entry.grid(row=0, column=1, sticky='w', padx=4, pady=4)
        lesson_label_entry.bind("<KeyRelease>", mark_changed)
        ttk.Checkbutton(general_frame, text="Вимкнути звуки у вихідні",
                        variable=mute_weekends_var,
                        command=mark_changed).grid(row=1, column=0, columnspan=2, sticky='w', padx=4, pady=4)
        ttk.Label(general_frame,
                  text="Порада: Якщо індивідуальний звук не задано — використовується дефолт.").grid(
            row=2, column=0, columnspan=2, sticky='w', padx=4, pady=10
        )
        general_frame.columnconfigure(1, weight=1)

        # ---- Кнопки збереження ----
        btn_bar = ttk.Frame(win)
        btn_bar.pack(fill='x', pady=6)

        def validate_and_collect_schedule():
            normal_new, friday_new = [], []
            for e_start, e_end in self.schedule_rows_normal:
                s = e_start.get().strip(); e = e_end.get().strip()
                if not s or not e:
                    messagebox.showerror("Помилка", "Порожнє поле часу у звичайному розкладі.")
                    return None
                normal_new.append([s, e])
            for e_start, e_end in self.schedule_rows_friday:
                s = e_start.get().strip(); e = e_end.get().strip()
                if not s or not e:
                    messagebox.showerror("Помилка", "Порожнє поле часу у п'ятничному розкладі.")
                    return None
                friday_new.append([s, e])
            return normal_new, friday_new

        def collect_lesson_sounds():
            out = {}
            for idx, start_entry, end_entry in self.lesson_sound_rows:
                s_path = start_entry.get().strip()
                e_path = end_entry.get().strip()
                obj = {}
                if s_path:
                    obj["start"] = s_path
                if e_path:
                    obj["end"] = e_path
                if obj:
                    out[str(idx)] = obj
            return out

        def apply_changes(close=False):
            result = validate_and_collect_schedule()
            if result is None:
                return
            normal_new, friday_new = result
            self.normal_schedule = normal_new
            self.friday_schedule = friday_new
            CONFIG["schedules"]["normal"] = normal_new
            CONFIG["schedules"]["friday"] = friday_new

            self.lesson_label = lesson_label_var.get().strip() or "Урок"
            self.mute_weekends = mute_weekends_var.get()
            CONFIG["lesson_label"] = self.lesson_label
            CONFIG["mute_weekends"] = self.mute_weekends

            self.lesson_sounds_cfg["defaults"]["start"] = def_start_var.get().strip()
            self.lesson_sounds_cfg["defaults"]["end"] = def_end_var.get().strip()
            self.lesson_sounds_cfg["lessons"] = collect_lesson_sounds()

            save_config(CONFIG)
            self.update_schedule_display()
            self._unsaved_changes = False
            if close:
                win.destroy()
            else:
                messagebox.showinfo("Збережено", "Зміни застосовано.")

        ttk.Button(btn_bar, text="✔ Застосувати",
                   command=lambda: apply_changes(False),
                   style='primary.TButton').pack(side='left', padx=5)
        ttk.Button(btn_bar, text="💾 Зберегти і закрити",
                   command=lambda: apply_changes(True),
                   style='primary.TButton').pack(side='left', padx=5)
        ttk.Button(btn_bar, text="Закрити без збереження",
                   command=lambda: (win.destroy() if (not self._unsaved_changes or
                                                      messagebox.askyesno("Підтвердження",
                                                                          "Є незбережені зміни. Закрити без збереження?"))
                                    else None)
                   ).pack(side='right', padx=5)

        def on_close():
            if self._unsaved_changes and not messagebox.askyesno("Підтвердження",
                                                                 "Є незбережені зміни. Закрити без збереження?"):
                return
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", on_close)

    def _browse_to_var(self, tk_var: tk.StringVar, changed_callback=None):
        path = filedialog.askopenfilename(
            title="Оберіть аудіо",
            filetypes=[("Аудіо файли", "*.mp3 *.wav")]
        )
        if path:
            tk_var.set(path)
            if changed_callback:
                changed_callback()

    # ==================== ЗВУКИ ПОВІТРЯНОЇ ТРИВОГИ ====================
    def open_alert_sound_settings(self):
        win = tk.Toplevel(self.master)
        win.title("Звуки тривог / хвилина мовчання")
        win.geometry("650x260")
        win.transient(self.master)
        win.grab_set()

        items = [
            ("air_alert", "Повітряна тривога"),
            ("air_clear", "Відбій тривоги"),
            ("silence", "Хвилина мовчання (09:00)")
        ]
        vars_map = {}
        for r, (key, label) in enumerate(items):
            ttk.Label(win, text=label).grid(row=r, column=0, sticky='w', padx=6, pady=6)
            var = tk.StringVar(value=self.alert_sounds_cfg.get(key, ""))
            entry = ttk.Entry(win, textvariable=var, width=50)
            entry.grid(row=r, column=1, padx=6, pady=6)
            ttk.Button(win, text="Обрати",
                       command=lambda v=var: self._browse_to_var(v)).grid(row=r, column=2, padx=4)
            ttk.Button(win, text="✖", width=3,
                       command=lambda v=var: v.set("")).grid(row=r, column=3, padx=3)
            vars_map[key] = var

        def play_temp(path):
            if not path:
                messagebox.showwarning("Увага", "Файл не вказано.")
                return
            try:
                pygame.mixer.music.load(path)
                pygame.mixer.music.set_volume(0 if self.muted else self.current_volume)
                pygame.mixer.music.play()
            except Exception as e:
                messagebox.showerror("Помилка", f"Не вдалося відтворити: {e}")

        for r, (key, _) in enumerate(items):
            ttk.Button(win, text="▶",
                       command=lambda k=key: play_temp(vars_map[k].get())).grid(row=r, column=4, padx=2)

        def save_alerts():
            for k, v in vars_map.items():
                self.alert_sounds_cfg[k] = v.get().strip()
            save_config(CONFIG)
            self.load_air_sounds()
            messagebox.showinfo("Готово", "Звуки тривог збережено.")
            win.destroy()

        ttk.Button(win, text="Зберегти", style='primary.TButton',
                   command=save_alerts).grid(row=len(items), column=0, columnspan=5, pady=12)

    # ==================== ЛОГІКА / ЧАС ====================
    def get_current_schedule(self):
        return self.friday_schedule if self.is_friday_schedule else self.normal_schedule

    def toggle_friday_mode(self):
        self.is_friday_schedule = not self.is_friday_schedule
        self.friday_toggle.config(
            text=("Перемкнути на звичайний розклад" if self.is_friday_schedule
                  else "Перемкнути на розклад п'ятниці"))
        self.update_schedule_display()

    def update_datetime(self):
        now = datetime.datetime.now()
        text = f"{UKRAINIAN_DAYS[now.weekday()]}\n{now.day} {UKRAINIAN_MONTHS[now.month]} {now.year}"
        self.lbl_day_info.config(text=text)
        self.master.after(1000, self.update_datetime)

    def time_to_seconds(self, t: str):
        if not t:
            return 0
        parts = list(map(int, t.split(':')))
        if len(parts) == 2:
            h, m = parts; s = 0
        else:
            h, m, s = parts
        return h * 3600 + m * 60 + s

    def update_clock(self):
        now = datetime.datetime.now()
        current_str = now.strftime("%H:%M:%S")
        self.lbl_current_time.config(text=current_str)
        current_sec = self.time_to_seconds(current_str)
        schedule = self.get_current_schedule()

        events = []
        for idx, (start, end) in enumerate(schedule, start=1):
            events.append((self.time_to_seconds(start + ":00"), idx, 'start'))
            events.append((self.time_to_seconds(end + ":00"), idx, 'end'))
        events.sort(key=lambda e: e[0])

        threshold = 2
        triggered = None
        for et, idx, etype in events:
            if current_sec <= et:
                if et - current_sec <= threshold:
                    key = (et, etype, idx)
                    if self.last_bell_played != key:
                        self.play_lesson_sound(idx, 'start' if etype == 'start' else 'end')
                        self.last_bell_played = key
                        triggered = (idx, etype)
                break

        if triggered:
            status = f"{self.lesson_label} {triggered[0]}: {'початок' if triggered[1]=='start' else 'завершення'}"
        else:
            upcoming = [e for e in events if e[0] > current_sec]
            if upcoming:
                n = upcoming[0]
                status = f"Скоро {'початок' if n[2]=='start' else 'кінець'} {self.lesson_label.lower()} {n[1]}"
            else:
                status = "Навчальний день завершено"
        self.lbl_lesson_status.config(text=status)

        # Хвилина мовчання
        special_dt = datetime.datetime.combine(now.date(), SPECIAL_EVENT_TIME)
        diff = (special_dt - now).total_seconds()
        if diff > 0:
            m, s = divmod(int(diff), 60)
            self.lbl_special_event.config(text=f"До хвилини мовчання: {m:02}:{s:02}")
        elif 0 >= diff > -60:
            if self.last_special_day != now.date():
                self.play_special_event()
                self.last_special_day = now.date()
                self.lbl_special_event.config(text="Хвилина мовчання зараз!")
        else:
            self.lbl_special_event.config(text="Хвилина мовчання сьогодні відбулась")

        self.master.after(200, self.update_clock)

    def stop_music(self):
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass

    def set_volume(self, value):
        self.current_volume = float(value)
        if not self.muted:
            pygame.mixer.music.set_volume(self.current_volume)
            try:
                self.air_alarm_channel.set_volume(self.current_volume)
            except Exception:
                pass

    def toggle_mute(self):
        self.muted = not self.muted
        if self.muted:
            pygame.mixer.music.set_volume(0)
            try:
                self.air_alarm_channel.set_volume(0)
            except Exception:
                pass
            if getattr(self, 'muted_icon', None):
                self.mute_button.config(image=self.muted_icon)
        else:
            pygame.mixer.music.set_volume(self.current_volume)
            try:
                self.air_alarm_channel.set_volume(self.current_volume)
            except Exception:
                pass
            if getattr(self, 'mute_icon', None):
                self.mute_button.config(image=self.mute_icon)

    def manual_air_alarm(self, state: bool):
        # Ручний тест (не враховує спадкування)
        self.update_region_status(state, manual=True)

    def _refresh_region_alert_display(self):
        """
        Викликається після зміни вибору регіону щоб одразу показати
        коректний (успадкований) стан тривоги.
        """
        rid = self.selected_region_id.get()
        self.update_region_status(self.is_region_alert_active(rid))

    # ==================== ПЕРЕВІРКА ТРИВОГ ====================
    def check_alerts(self):
        headers = CaseInsensitiveDict()
        headers["Authorization"] = API_KEY
        self._active_alert_ids = set()
        try:
            resp = requests.get("https://api.ukrainealarm.com/api/v3/alerts",
                                headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                self.alert_listbox.delete(0, 'end')
                for alert in data:
                    rid = str(alert.get('regionId', ''))
                    name = alert.get('regionName', '')
                    if rid:
                        self._active_alert_ids.add(rid)
                    self.alert_listbox.insert('end', name)
            else:
                logging.warning(f"[ALERTS] HTTP {resp.status_code}")
        except Exception as e:
            logging.error(f"[ALERTS] {e}")

        selected_id = self.selected_region_id.get()
        active = self.is_region_alert_active(selected_id)
        self.update_region_status(active)

    # ==================== СЕРВІСИ ====================
    def start_services(self):
        self.update_datetime()
        self.update_clock()
        self.start_alert_checker()

    def start_alert_checker(self):
        def loop():
            while True:
                self.check_alerts()
                time.sleep(5)
        threading.Thread(target=loop, daemon=True).start()

    # ==================== СИСТЕМНІ ДІЇ / ТРЕЙ ====================
    def on_close(self):
        self.hide_window()

    def hide_window(self):
        self.master.withdraw()
        self.show_notification("CloudBell App", "Програму згорнуто в трей.")
        self.create_tray_icon()

    def create_tray_icon(self):
        """
        Створює tray іконку (якщо ще не створена).
        Викликати при мінімізації / приховуванні вікна.
        """
        # Якщо вже є діюча іконка – не дублюємо
        if getattr(self, 'tray_icon', None):
            try:
                if self.tray_icon.visible:
                    return
            except Exception:
                pass

        # Пробуємо ICO, далі PNG
        ico_path = resource_path("tray_icon.ico")
        png_path = resource_path("tray_icon.png")

        image = None
        for p in (ico_path, png_path):
            if os.path.exists(p):
                try:
                    image = Image.open(p).copy()
                    break
                except Exception as e:
                    logging.warning(f"[TRAY] Не вдалося відкрити {p}: {e}")

        if image is None:
            # fallback: простий однотонний квадратик
            image = Image.new("RGBA", (64, 64), (40, 40, 40, 255))

        # Зберігаємо посилання, щоб GC не зібрав
        self._tray_icon_image = image

        def on_open(icon, item):
            self.show_window()

        def on_exit(icon, item):
            try:
                icon.stop()
            except Exception:
                pass
            self.master.after(10, self.master.quit)

        menu = pystray.Menu(
            MenuItem("Відкрити", on_open),
            MenuItem("Вийти", on_exit)
        )

        self.tray_icon = pystray.Icon(
            "cloudbell_tray",
            self._tray_icon_image,
            "CloudBell App",
            menu
        )
        # Запускаємо у потоці
        threading.Thread(target=self.tray_icon.run, daemon=True).start()
        logging.info("[TRAY] Іконка створена")

    def minimize_to_tray(self):
        """
        Ховає вікно і створює tray іконку.
        Викличте з обробника кнопки закриття (WM_DELETE_WINDOW).
        """
        try:
            self.master.withdraw()
        except Exception as e:
            logging.error(f"[TRAY] withdraw error: {e}")
        self.create_tray_icon()

    def show_window(self, icon=None, item=None):
        """
        Показує головне вікно та зупиняє tray (щоб не залишалась “мертва” іконка).
        """
        try:
            self.master.deiconify()
            self.master.lift()
            self.master.focus_force()
        except Exception:
            pass
        if getattr(self, 'tray_icon', None):
            try:
                self.tray_icon.stop()
            except Exception:
                pass
            self.tray_icon = None
        logging.info("[TRAY] Вікно показано")

    def exit_app(self, icon=None, item=None):
        """
        Коректне завершення (виклик із меню трею чи десь).
        """
        if getattr(self, 'tray_icon', None):
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.master.quit()

    def show_notification(self, title, message):
        """
        Показ системного повідомлення з іконкою.
        Plyer на Windows відображає іконку краще, якщо це .ico.
        """
        try:
            icon_candidate = None
            for p in ("tray_icon.ico", "school_icon.ico", "tray_icon.png", "school_icon.png"):
                rp = resource_path(p)
                if os.path.exists(rp):
                    icon_candidate = rp
                    break

            notification.notify(
                title=title,
                message=message,
                app_name="CloudBell App",
                app_icon=icon_candidate,
                timeout=5
            )
            logging.debug(f"[NOTIFY] OK (icon={icon_candidate})")
        except Exception as e:
            logging.error(f"[NOTIFY] Не вдалося показати повідомлення: {e}")


    # ==================== ДОДАТКОВІ ДІЇ ====================
    def select_custom_logo(self):
        path = filedialog.askopenfilename(
            title="Оберіть логотип закладу",
            filetypes=[("Зображення", "*.png *.jpg *.jpeg *.gif *.ico")]
        )
        if path:
            try:
                dst = os.path.join(CONFIG_DIR, "school_logo.png")
                shutil.copy(path, dst)
                img = Image.open(dst).resize((200, 350), Image.Resampling.LANCZOS)
                self.logo_img = ImageTk.PhotoImage(img)
                self.logo_label.config(image=self.logo_img)
                CONFIG["school_logo"] = dst
                save_config(CONFIG)
            except Exception as e:
                logging.error(f"[LOGO] {e}")
                messagebox.showerror("Помилка", "Не вдалося встановити логотип.")

# ----------------------- ЗАПУСК -----------------------
if __name__ == "__main__":
    root = tk.Tk()
    app = CloudBellApp(root)
    root.mainloop()
    logging.info("Додаток завершено.")