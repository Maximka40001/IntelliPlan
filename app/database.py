"""
Database connection and session management
Supports both SQLite and PostgreSQL
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from app.config import DATABASE_TYPE, DATABASE_URL_A, DATABASE_URL_B
from app.models import Base

# Создаём движки для БД A и БД B
if DATABASE_TYPE == "sqlite":
    # SQLite: две отдельные базы данных
    engine_a = create_engine(DATABASE_URL_A, connect_args={"check_same_thread": False})
    engine_b = create_engine(DATABASE_URL_B, connect_args={"check_same_thread": False})
    
    # Включаем поддержку внешних ключей для SQLite
    @event.listens_for(engine_a, "connect")
    def set_sqlite_pragma_a(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    
    @event.listens_for(engine_b, "connect")
    def set_sqlite_pragma_b(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
else:
    # PostgreSQL: одна база данных, разные схемы
    engine_a = create_engine(DATABASE_URL_A, pool_pre_ping=True)
    engine_b = engine_a  # Используем тот же движок
    
    # Создаём схемы, если их нет
    with engine_a.connect() as conn:
        conn.execute("CREATE SCHEMA IF NOT EXISTS source_data")
        conn.execute("CREATE SCHEMA IF NOT EXISTS schedule_data")
        conn.commit()

# Создаём фабрики сессий
SessionLocalA = sessionmaker(autocommit=False, autoflush=False, bind=engine_a)
SessionLocalB = sessionmaker(autocommit=False, autoflush=False, bind=engine_b)

def get_db_a():
    """Dependency для получения сессии БД A"""
    db = SessionLocalA()
    try:
        yield db
    finally:
        db.close()

def get_db_b():
    """Dependency для получения сессии БД B"""
    db = SessionLocalB()
    try:
        yield db
    finally:
        db.close()

def init_databases():
    """Инициализация таблиц в базах данных"""
    print("Инициализация баз данных...")
    
    if DATABASE_TYPE == "sqlite":
        # Для SQLite создаём таблицы в обеих базах
        print("  Создание таблиц в database_a.db...")
        Base.metadata.create_all(bind=engine_a)
        
        print("  Создание таблиц в database_b.db...")
        Base.metadata.create_all(bind=engine_b)
    else:
        # Для PostgreSQL создаём все таблицы в одной базе (с разными схемами)
        print("  Создание таблиц в PostgreSQL...")
        Base.metadata.create_all(bind=engine_a)
    
    print("✓ Базы данных инициализированы")
