#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CloudBell App - Raspberry Pi Receiver
Скрипт для отримання та відтворення звуку з хмари на Raspberry Pi
"""

import sys
import os
import json
import asyncio
import websockets
import pyaudio
import base64
import threading
import queue
import logging
from datetime import datetime

# Налаштування логування
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Налаштування аудіо
AUDIO_CHUNK_SIZE = 1024
AUDIO_FORMAT = pyaudio.paInt16
AUDIO_CHANNELS = 1
AUDIO_RATE = 44100

class RaspberryPiReceiver:
    """
    Клас для отримання звуку з хмари на Raspberry Pi.
    """
    
    def __init__(self, server_url: str):
        self.server_url = server_url
        self.is_receiving = False
        self.websocket = None
        self.audio_queue = queue.Queue()
        self.stream = None
        self.p = None
        
    def start_receiving(self):
        """
        Починає отримання звуку з хмари.
        """
        if self.is_receiving:
            return
            
        try:
            # Ініціалізуємо PyAudio
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
            threading.Thread(target=self.websocket_client, daemon=True).start()
            
            # Запускаємо відтворення аудіо
            threading.Thread(target=self.play_audio, daemon=True).start()
            
            logging.info("[RASPBERRY_PI] Отримання звуку розпочато")
            return True
            
        except Exception as e:
            logging.error(f"[RASPBERRY_PI] Помилка запуску: {e}")
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
            
        logging.info("[RASPBERRY_PI] Отримання звуку зупинено")
    
    def websocket_client(self):
        """
        WebSocket клієнт для отримання аудіо.
        """
        async def receive_audio():
            try:
                async with websockets.connect(self.server_url) as websocket:
                    self.websocket = websocket
                    logging.info("[RASPBERRY_PI] Підключено до сервера")
                    
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
                            logging.error(f"[RASPBERRY_PI] Помилка обробки: {e}")
                            
            except Exception as e:
                logging.error(f"[RASPBERRY_PI] Помилка підключення: {e}")
        
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
                logging.error(f"[RASPBERRY_PI] Помилка відтворення: {e}")
                break

def main():
    """
    Головна функція для запуску на Raspberry Pi.
    """
    print("🍓 CloudBell App - Raspberry Pi Receiver")
    print("=" * 50)
    
    # URL сервера (можна змінити)
    server_url = input("Введіть URL WebSocket сервера (Enter для за замовчуванням): ").strip()
    if not server_url:
        server_url = "wss://cloudbell-audio-server.herokuapp.com/ws"
    
    print(f"Підключення до сервера: {server_url}")
    
    # Створюємо ресивер
    receiver = RaspberryPiReceiver(server_url)
    
    try:
        # Запускаємо отримання звуку
        if receiver.start_receiving():
            print("✅ Отримання звуку розпочато. Натисніть Ctrl+C для зупинки.")
            
            # Очікуємо сигнал зупинки
            while True:
                try:
                    import time
                    time.sleep(1)
                except KeyboardInterrupt:
                    break
        else:
            print("❌ Не вдалося розпочати отримання звуку!")
            
    except KeyboardInterrupt:
        print("\n🛑 Зупинка...")
    except Exception as e:
        print(f"❌ Помилка: {e}")
    finally:
        receiver.stop_receiving()
        print("👋 Завершено!")

if __name__ == "__main__":
    main()
