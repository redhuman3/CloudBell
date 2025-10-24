# 🌐 Розгортання публічного WebSocket сервера

## Швидкий старт: Railway.app

### Крок 1: Підготовка коду

Створіть файл `requirements_server.txt`:
```
websockets==12.0
```

Створіть файл `railway.json`:
```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "python websocket_server.py",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

### Крок 2: Деплой на Railway

1. Зареєструйтесь на https://railway.app
2. Створіть новий проект "New Project"
3. Виберіть "Deploy from GitHub repo"
4. Виберіть ваш репозиторій
5. Railway автоматично розгорне сервер
6. Отримайте публічний URL

### Крок 3: Налаштування

1. В CloudBell App відкрийте налаштування хмарної трансляції
2. Введіть публічний URL: `wss://your-app.railway.app`
3. Збережіть зміни

## Альтернатива: Heroku

### 1. Створіть файли:

**Procfile**:
```
web: python websocket_server.py
```

**runtime.txt**:
```
python-3.13.2
```

### 2. Деплой:

```bash
heroku login
heroku create cloudbell-audio
git init
git add .
git commit -m "Initial commit"
git push heroku main
```

### 3. Отримайте URL:

```bash
heroku info
```

Використайте URL типу: `wss://cloudbell-audio.herokuapp.com`

## Безпека (рекомендовано)

### Додайте автентифікацію в websocket_server.py:

```python
async def handler(websocket, path):
    # Перевірка токену
    token = websocket.request_headers.get('Authorization')
    if token != 'your-secret-token-here':
        await websocket.close(code=4001, reason="Unauthorized")
        return
    
    # Решта коду...
```

### В CloudBell App додайте токен:

В методі `websocket_client` додайте заголовки:
```python
async with websockets.connect(
    server_url,
    extra_headers={"Authorization": "your-secret-token-here"}
) as websocket:
```

## Перевірка роботи

1. Запустіть CloudBell App на вашому ПК
2. Налаштуйте публічний URL сервера
3. Розпочніть трансляцію
4. На Raspberry Pi запустіть `raspberry_pi_receiver.py` з тим же URL
5. Аудіо повинно передаватися через інтернет!

## Розбіжності між локальним та публічним сервером

| Локальний | Публічний |
|-----------|-----------|
| `ws://localhost:8765` | `wss://your-app.railway.app` |
| Тільки в локальній мережі | Доступ з будь-якого місця |
| Без автентифікації | З автентифікацією |
| ws:// (небезпечний) | wss:// (безпечний) |

## Поради

- ✅ Завжди використовуйте WSS для публічних серверів
- ✅ Додайте автентифікацію для безпеки
- ✅ Обмежте кількість одночасних підключень
- ✅ Використовуйте environment variables для токенів
- ✅ Налаштуйте моніторинг та логування

## Підтримка

Якщо виникли проблеми:
1. Перевірте логи сервера
2. Перевірте чи відкритий порт
3. Перевірте підключення до інтернету
4. Перевірте чи використовується правильний протокол (ws/wss)

