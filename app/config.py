# Configuration settings
import os
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

load_dotenv()

# Database settings
DATABASE_TYPE = os.getenv("DATABASE_TYPE", "sqlite")

# SQLite settings
SQLITE_DB_A = os.getenv("SQLITE_DB_A", "database_a.db")
SQLITE_DB_B = os.getenv("SQLITE_DB_B", "database_b.db")

# PostgreSQL settings
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "schedule_db")

# Build database URLs
if DATABASE_TYPE == "postgresql":
    DATABASE_URL_A = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    DATABASE_URL_B = DATABASE_URL_A
else:
    DATABASE_URL_A = f"sqlite:///{SQLITE_DB_A}"
    DATABASE_URL_B = f"sqlite:///{SQLITE_DB_B}"

# ============================================================================
# УЧЕБНЫЙ ГОД 2025-2026
# ============================================================================
ACADEMIC_YEAR_START = date(2025, 9, 1)   # Начало учебного года
ACADEMIC_YEAR_END = date(2026, 6, 30)    # Конец учебного года

# Праздники и выходные дни в России 2025-2026
HOLIDAYS_2025_2026 = [
    # 2025 год
    date(2025, 1, 1), date(2025, 1, 2), date(2025, 1, 3), date(2025, 1, 4),
    date(2025, 1, 5), date(2025, 1, 6), date(2025, 1, 7), date(2025, 1, 8),  # Новогодние каникулы
    date(2025, 2, 23),  # День защитника Отечества
    date(2025, 3, 8),   # Международный женский день
    date(2025, 5, 1),   # Праздник Весны и Труда
    date(2025, 5, 9),   # День Победы
    date(2025, 6, 12),  # День России
    date(2025, 11, 4),  # День народного единства
    # Осенние каникулы - примерно неделя в конце октября
    date(2025, 10, 27), date(2025, 10, 28), date(2025, 10, 29), 
    date(2025, 10, 30), date(2025, 10, 31), date(2025, 11, 1), date(2025, 11, 2),
    # Зимние каникулы 2025-2026
    date(2025, 12, 29), date(2025, 12, 30), date(2025, 12, 31),
    # 2026 год
    date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3), date(2026, 1, 4),
    date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7), date(2026, 1, 8),  # Новогодние каникулы
    # Весенние каникулы - примерно неделя в конце марта
    date(2026, 3, 23), date(2026, 3, 24), date(2026, 3, 25), 
    date(2026, 3, 26), date(2026, 3, 27), date(2026, 3, 28), date(2026, 3, 29),
    date(2026, 2, 23),  # День защитника Отечества
    date(2026, 3, 8),   # Международный женский день
    date(2026, 5, 1),   # Праздник Весны и Труда
    date(2026, 5, 9),   # День Победы
    date(2026, 6, 12),  # День России
]

def get_working_days():
    """Получить список всех рабочих дней учебного года (исключая выходные и праздники)"""
    working_days = []
    current = ACADEMIC_YEAR_START
    
    while current <= ACADEMIC_YEAR_END:
        # Проверяем: не выходной (сб, вс) и не праздник
        if current.weekday() < 5 and current not in HOLIDAYS_2025_2026:
            working_days.append(current)
        current += timedelta(days=1)
    
    return working_days

# Получаем все рабочие дни
WORKING_DAYS = get_working_days()
TOTAL_WORKING_DAYS = len(WORKING_DAYS)

def get_semester_mondays(semester: int):
    """Вернуть список понедельников для заданного семестра"""
    mondays = []
    for d in WORKING_DAYS:
        if d.weekday() != 0:
            continue
        if semester == 1 and d < date(2026, 1, 1):
            mondays.append(d)
        elif semester == 2 and d >= date(2026, 1, 9):
            mondays.append(d)
    return mondays

SEMESTER_1_MONDAYS = get_semester_mondays(1)  # 16 недель  сен-дек 2025
SEMESTER_2_MONDAYS = get_semester_mondays(2)  # 23 недели  янв-июн 2026

# ============================================================================
# ПАРАМЕТРЫ РАСПИСАНИЯ - ДВЕ СМЕНЫ
# ============================================================================

# 1 смена (5 пар) + 2 смена (4 пары) = 9 пар в день
SLOTS_PER_DAY = 9

# Расписание звонков
SLOT_TIMES = [
    # 1 смена
    '08:30-10:00',   # 1 пара
    '10:10-11:40',   # 2 пара
    '12:10-13:40',   # 3 пара (пересекается со 2 сменой)
    '13:50-15:20',   # 4 пара (пересекается со 2 сменой)
    '15:30-17:00',   # 5 пара (пересекается со 2 сменой)
    # 2 смена (индексы 5-8)
    '12:10-13:40',   # 1 пара 2 смены (= 3 пара 1 смены)
    '13:50-15:20',   # 2 пара 2 смены (= 4 пара 1 смены)
    '15:30-17:00',   # 3 пара 2 смены (= 5 пара 1 смены)
    '17:10-18:40',   # 4 пара 2 смены
]

# Смены: какие слоты относятся к какой смене
SHIFT_1_SLOTS = [0, 1, 2, 3, 4]  # 1 смена: слоты 0-4
SHIFT_2_SLOTS = [5, 6, 7, 8]      # 2 смена: слоты 5-8

# Пересекающиеся слоты (нельзя использовать одновременно)
OVERLAPPING_SLOTS = {
    2: [5],  # 3 пара 1 смены = 1 пара 2 смены
    3: [6],  # 4 пара 1 смены = 2 пара 2 смены
    4: [7],  # 5 пара 1 смены = 3 пара 2 смены
    5: [2],  # 1 пара 2 смены = 3 пара 1 смены
    6: [3],  # 2 пара 2 смены = 4 пара 1 смены
    7: [4],  # 3 пара 2 смены = 5 пара 1 смены
}

# Названия дней недели
DAY_NAMES = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница']

def get_date_info(working_day_index):
    """Получить информацию о дате по индексу рабочего дня"""
    if 0 <= working_day_index < len(WORKING_DAYS):
        date_obj = WORKING_DAYS[working_day_index]
        return {
            'date': date_obj,
            'day_name': DAY_NAMES[date_obj.weekday()],
            'month': date_obj.month,
            'year': date_obj.year,
            'weekday': date_obj.weekday()
        }
    return None

def get_semester_for_date(date_obj):
    """Определить семестр для даты (1 или 2)"""
    # Первый семестр: сентябрь - декабрь
    # Второй семестр: январь - июнь (следующего года)
    if date_obj.month >= 9 or (date_obj.month == 1 and date_obj.year == ACADEMIC_YEAR_START.year):
        return 1
    else:
        return 2

def is_date_past(date_obj):
    """Проверить, прошла ли дата"""
    return date_obj < date.today()

def get_shift_name(slot_idx):
    """Получить название смены по индексу слота"""
    if slot_idx in SHIFT_1_SLOTS:
        return "1 смена"
    elif slot_idx in SHIFT_2_SLOTS:
        return "2 смена"
    return "Неизвестно"
