"""
Database models using SQLAlchemy ORM
Works with both SQLite and PostgreSQL
"""
from sqlalchemy import Column, Integer, String, Float, Date, Boolean, ForeignKey, DateTime, Text, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
import os
import enum

Base = declarative_base()

USE_POSTGRES = os.getenv("DATABASE_TYPE", "sqlite") == "postgresql"

# Роли пользователей
class UserRole(enum.Enum):
    ADMIN = "admin"
    EDUCATIONAL_DEPT = "educational_dept"
    STUDENT = "student"

# ========== База A (исходные данные) ==========

class Teacher(Base):
    __tablename__ = 'teachers'
    if USE_POSTGRES:
        __table_args__ = {'schema': 'source_data'}
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    surname = Column(String(255), nullable=False)  # Фамилия преподавателя
    max_hours_per_week = Column(Integer, default=30)
    max_consecutive_pairs = Column(Integer, default=2)

class StudentGroup(Base):
    __tablename__ = 'student_groups'
    if USE_POSTGRES:
        __table_args__ = {'schema': 'source_data'}
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    size = Column(Integer, nullable=False)
    max_hours_per_week = Column(Integer, default=30)

class Subject(Base):
    __tablename__ = 'subjects'
    if USE_POSTGRES:
        __table_args__ = {'schema': 'source_data'}
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    hours_per_semester = Column(Integer, nullable=False)  # Часов в семестр (вместо hours_per_week)
    semester = Column(Integer, nullable=False, default=1)  # Номер семестра (1 или 2)

class Classroom(Base):
    __tablename__ = 'classrooms'
    if USE_POSTGRES:
        __table_args__ = {'schema': 'source_data'}
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    capacity = Column(Integer, nullable=False)
    type = Column(String(50), nullable=False)

class GroupSubject(Base):
    """Связь: группа - предмет - преподаватель"""
    __tablename__ = 'group_subjects'
    if USE_POSTGRES:
        __table_args__ = {'schema': 'source_data'}
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(Integer, nullable=False)
    subject_id = Column(Integer, nullable=False)
    teacher_id = Column(Integer, nullable=False)
    hours_per_semester = Column(Integer, nullable=False)  # Часов в семестр
    semester = Column(Integer, nullable=False, default=1)  # В каком семестре преподается

# ========== База B (результаты расписания) ==========

class Schedule(Base):
    """Расписание занятий"""
    __tablename__ = 'schedule'
    if USE_POSTGRES:
        __table_args__ = {'schema': 'schedule_data'}
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(Integer, nullable=False)
    group_name = Column(String(100), nullable=False)
    subject_id = Column(Integer, nullable=False)
    subject_name = Column(String(255), nullable=False)
    teacher_id = Column(Integer, nullable=False)
    teacher_name = Column(String(255), nullable=False)
    
    # Дата и время
    date = Column(Date, nullable=False)  # Конкретная дата занятия
    day_name = Column(String(50), nullable=False)  # Название дня недели
    slot_idx = Column(Integer, nullable=False)  # Индекс пары (0, 1, 2)
    time = Column(String(50), nullable=False)  # Время пары
    
    # Аудитория
    classroom_id = Column(Integer, nullable=False)
    classroom = Column(String(100), nullable=False)
    
    # Семестр
    semester = Column(Integer, nullable=False)  # Номер семестра
    
    # Служебные поля
    created_at = Column(DateTime, default=func.now())

class CompletedHours(Base):
    """Учет вычитанных часов по предметам"""
    __tablename__ = 'completed_hours'
    if USE_POSTGRES:
        __table_args__ = {'schema': 'schedule_data'}
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(Integer, nullable=False)
    subject_id = Column(Integer, nullable=False)
    teacher_id = Column(Integer, nullable=False)
    semester = Column(Integer, nullable=False)
    
    # Дата занятия
    date = Column(Date, nullable=False)
    
    # Количество часов (обычно 2 часа = 1 пара)
    hours = Column(Integer, nullable=False, default=2)
    
    # Ссылка на запись в расписании
    schedule_id = Column(Integer, nullable=True)
    
    created_at = Column(DateTime, default=func.now())

class TeacherAbsence(Base):
    """Учет отсутствия преподавателей"""
    __tablename__ = 'teacher_absences'
    if USE_POSTGRES:
        __table_args__ = {'schema': 'schedule_data'}
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    teacher_id = Column(Integer, nullable=False)
    teacher_surname = Column(String(255), nullable=False)
    
    # Даты отсутствия
    absence_start = Column(Date, nullable=False)
    absence_end = Column(Date, nullable=False)
    
    # Причина (опционально)
    reason = Column(Text, nullable=True)
    
    # Флаг обработки
    processed = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=func.now())

class User(Base):
    """Пользователи системы"""
    __tablename__ = 'users'
    if USE_POSTGRES:
        __table_args__ = {'schema': 'schedule_data'}
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False)  # admin, educational_dept, student
    full_name = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=func.now())
