#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Утиліта для генерації ліцензійних ключів CloudBell App
"""

import hashlib
import base64
import json
import datetime

MASTER_SECRET = "CloudBell2025SecretKey"

def generate_license_key(organization_name: str, user_email: str) -> str:
    """
    Генерує ліцензійний ключ для організації.
    """
    data = f"{organization_name}|{user_email}|{MASTER_SECRET}"
    hash_obj = hashlib.sha256(data.encode())
    key = base64.b64encode(hash_obj.digest()).decode()[:32]
    return f"CB-{key}"

def main():
    print("🔐 Генератор ліцензійних ключів CloudBell App")
    print("=" * 50)
    
    while True:
        print("\nВведіть дані для генерації ключа:")
        org = input("Назва організації: ").strip()
        email = input("Email: ").strip()
        
        if not org or not email:
            print("❌ Помилка: Заповніть всі поля!")
            continue
        
        # Генеруємо ключ
        license_key = generate_license_key(org, email)
        
        print(f"\n✅ Ліцензійний ключ згенеровано:")
        print(f"Організація: {org}")
        print(f"Email: {email}")
        print(f"Ключ: {license_key}")
        
        # Зберігаємо в файл
        license_data = {
            'key': license_key,
            'organization': org,
            'email': email,
            'generated_date': datetime.datetime.now().isoformat()
        }
        
        filename = f"license_{org.replace(' ', '_')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(license_data, f, ensure_ascii=False, indent=2)
        
        print(f"💾 Дані збережено в файл: {filename}")
        
        choice = input("\nЗгенерувати ще один ключ? (y/n): ").strip().lower()
        if choice != 'y':
            break
    
    print("\n👋 До побачення!")

if __name__ == "__main__":
    main()
