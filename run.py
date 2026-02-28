"""
Главный скрипт запуска приложения
Инициализирует базы данных, создает пользователей и запускает сервер
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import init_databases
from app.main import app, create_default_users
import uvicorn

if __name__ == "__main__":
    print("=" * 80)
    print("ЗАПУСК СИСТЕМЫ УПРАВЛЕНИЯ РАСПИСАНИЕМ")
    print("=" * 80)
    
    ## Инициализация баз данных
    #print("\n1. Инициализация баз данных...")
    #init_databases()
    
    ## Создание пользователей по умолчанию
    #print("\n2. Создание пользователей...")
    #create_default_users()
    #
    #print("\n" + "=" * 80)
    #print("ПОЛЬЗОВАТЕЛИ ДЛЯ ВХОДА:")
    #print("  • admin / admin123 - Администратор (полный доступ)")
    #print("  • teacher / teacher123 - Учебная часть (генерация, просмотр, чат)")
    #print("  • student / student123 - Студент (только просмотр)")
    #print("=" * 80)
    
    # Запуск сервера
    print("\n3. Запуск веб-сервера...")
    print("   → Открывайте в браузере: http://localhost:8000")
    print("\n" + "=" * 80)
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
