#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CloudBell App - WebSocket Server
Простий сервер для тестування хмарної трансляції звуку
"""

import asyncio
import websockets
import json
import logging
import os
from datetime import datetime

# Налаштування логування
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class AudioServer:
    """
    WebSocket сервер для трансляції аудіо.
    """
    
    def __init__(self):
        self.connected_clients = set()
        self.audio_data = None
        
    async def register_client(self, websocket):
        """
        Реєструє нового клієнта.
        """
        self.connected_clients.add(websocket)
        logging.info(f"Клієнт підключено. Всього клієнтів: {len(self.connected_clients)}")
        
    async def unregister_client(self, websocket):
        """
        Відключає клієнта.
        """
        self.connected_clients.discard(websocket)
        logging.info(f"Клієнт відключено. Всього клієнтів: {len(self.connected_clients)}")
        
    async def handle_client(self, websocket, path):
        """
        Обробляє підключення клієнта.
        """
        await self.register_client(websocket)
        
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    
                    if data.get('type') == 'audio':
                        # Зберігаємо аудіо дані
                        self.audio_data = data
                        
                        # Розсилаємо всім підключеним клієнтам
                        if self.connected_clients:
                            message_to_send = json.dumps(data)
                            disconnected = set()
                            
                            for client in self.connected_clients:
                                try:
                                    await client.send(message_to_send)
                                except websockets.exceptions.ConnectionClosed:
                                    disconnected.add(client)
                            
                            # Видаляємо відключених клієнтів
                            for client in disconnected:
                                self.connected_clients.discard(client)
                    
                    elif data.get('type') == 'sound_event':
                        # Обробляємо події відтворення звуків
                        logging.info(f"🎵 Звук: {data.get('file')} ({data.get('event')})")
                        
                        # Розсилаємо всім підключеним клієнтам
                        if self.connected_clients:
                            message_to_send = json.dumps(data)
                            disconnected = set()
                            
                            for client in self.connected_clients:
                                try:
                                    await client.send(message_to_send)
                                except websockets.exceptions.ConnectionClosed:
                                    disconnected.add(client)
                            
                            # Видаляємо відключених клієнтів
                            for client in disconnected:
                                self.connected_clients.discard(client)
                                
                    elif data.get('type') == 'ping':
                        # Відповідаємо на ping
                        await websocket.send(json.dumps({'type': 'pong'}))
                        
                except json.JSONDecodeError:
                    logging.error("Невірний JSON")
                except Exception as e:
                    logging.error(f"Помилка обробки повідомлення: {e}")
                    
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            await self.unregister_client(websocket)

async def main():
    """
    Головна функція сервера.
    """
    server = AudioServer()
    
    # Отримуємо порт з environment змінної (для хмарних сервісів)
    PORT = int(os.environ.get("PORT", 8765))
    
    print("CloudBell App - WebSocket Server")
    print("=" * 50)
    print(f"Сервер запущено на ws://0.0.0.0:{PORT}")
    print("Для зупинки натисніть Ctrl+C")
    print("=" * 50)
    
    # Запускаємо сервер на всіх інтерфейсах (0.0.0.0)
    async with websockets.serve(server.handle_client, "0.0.0.0", PORT):
        await asyncio.Future()  # Запускаємо назавжди

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nСервер зупинено!")
