#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HTTP Audio Streaming Server для CloudBell
Віддає аудіо файли по HTTP для програвання в браузері
"""

import os
import json
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import socketserver

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class AudioStreamHandler(BaseHTTPRequestHandler):
    """Обробник HTTP запитів для стрімінгу аудіо"""
    
    def do_GET(self):
        """Обробляє GET запити"""
        try:
            parsed_path = urlparse(self.path)
            
            # CORS заголовки
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            
            if parsed_path.path == '/stream':
                # Потоковий аудіо файл
                self.handle_stream()
            elif parsed_path.path == '/files':
                # Список доступних файлів
                self.handle_list_files()
            elif parsed_path.path == '/ping':
                # Ping для перевірки доступності
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'status': 'ok'}).encode())
            else:
                self.send_error(404, "Not Found")
                
        except Exception as e:
            logging.error(f"Помилка обробки запиту: {e}")
            self.send_error(500, str(e))
    
    def do_OPTIONS(self):
        """Обробляє OPTIONS запити для CORS"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def handle_stream(self):
        """Обробляє потоки аудіо"""
        query_params = parse_qs(urlparse(self.path).query)
        filename = query_params.get('file', [''])[0]
        
        if not filename:
            self.send_error(400, "Missing file parameter")
            return
        
        # Шукаємо файл
        file_path = self.find_audio_file(filename)
        
        if not file_path or not os.path.exists(file_path):
            logging.warning(f"Файл не знайдено: {filename}")
            self.send_error(404, "File not found")
            return
        
        try:
            # Читаємо файл
            with open(file_path, 'rb') as f:
                audio_data = f.read()
            
            # Визначаємо MIME тип
            mime_type = self.get_mime_type(filename)
            
            # Відправляємо файл
            self.send_response(200)
            self.send_header('Content-Type', mime_type)
            self.send_header('Content-Length', str(len(audio_data)))
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.end_headers()
            self.wfile.write(audio_data)
            
            logging.info(f"Відправлено аудіо: {filename} ({len(audio_data)} bytes)")
            
        except Exception as e:
            logging.error(f"Помилка відправки файлу: {e}")
            self.send_error(500, str(e))
    
    def handle_list_files(self):
        """Повертає список доступних аудіо файлів"""
        audio_dir = os.path.dirname(__file__)
        audio_files = []
        
        for ext in ['.mp3', '.wav', '.ogg']:
            for file in Path(audio_dir).glob(f'*{ext}'):
                audio_files.append(file.name)
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'files': audio_files}).encode())
    
    def find_audio_file(self, filename):
        """Знаходить файл в різних місцях"""
        search_paths = [
            os.path.join(os.path.dirname(__file__), filename),
            os.path.join(os.path.expanduser('~'), 'AppData', 'Roaming', 'CloudBell', filename),
            filename
        ]
        
        for path in search_paths:
            if os.path.exists(path):
                return path
        
        return None
    
    def get_mime_type(self, filename):
        """Визначає MIME тип файлу"""
        ext = os.path.splitext(filename)[1].lower()
        mime_types = {
            '.mp3': 'audio/mpeg',
            '.wav': 'audio/wav',
            '.ogg': 'audio/ogg',
            '.m4a': 'audio/mp4',
        }
        return mime_types.get(ext, 'audio/mpeg')
    
    def log_message(self, format, *args):
        """Приховує стандартні повідомлення логування"""
        pass

def run_server(port=8765):
    """Запускає HTTP сервер"""
    server_address = ('0.0.0.0', port)
    httpd = HTTPServer(server_address, AudioStreamHandler)
    
    logging.info(f"🎵 HTTP Audio Stream Server запущено на http://0.0.0.0:{port}")
    logging.info(f"🔗 Приклад: http://localhost:{port}/stream?file=bell_start.mp3")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logging.info("🛑 Сервер зупинено")

if __name__ == '__main__':
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    run_server(port)
