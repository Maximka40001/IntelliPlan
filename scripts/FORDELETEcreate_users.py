"""
Скрипт создания/обновления пользователей в системе
Добавляет роль 'teacher' для конкретных преподавателей из БД А

Роли:
  admin           — Полный доступ
  educational_dept — Учебная часть (генерация, AI, просмотр)
  teacher         — Преподаватель (своё расписание + свои часы)
  student         — Студент (расписание всех групп, только чтение)

Запуск: python scripts/create_users.py
"""
import sys, os, hashlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocalA, SessionLocalB
from app.models import Teacher, User


def hash_password(p: str) -> str:
    return hashlib.sha256(p.encode()).hexdigest()


def create_or_update_user(db, username, password, role, full_name):
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        existing.password_hash = hash_password(password)
        existing.role = role
        existing.full_name = full_name
        print(f"  ✏️  Обновлён: {username} ({role})")
    else:
        db.add(User(
            username=username,
            password_hash=hash_password(password),
            role=role,
            full_name=full_name
        ))
        print(f"  ✅ Создан:   {username} ({role})")


def main():
    db_b = SessionLocalB()
    db_a = SessionLocalA()

    print("=" * 60)
    print("УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ INTELLIPLAN")
    print("=" * 60)

    # ── Базовые системные пользователи ─────────────────────────
    print("\n[Системные пользователи]")
    create_or_update_user(db_b, "admin",   "admin123",   "admin",            "Администратор")
    create_or_update_user(db_b, "edu",     "edu123",     "educational_dept", "Учебная часть")
    create_or_update_user(db_b, "student", "student123", "student",          "Студент Тестовый")

    # ── Пользователи-преподаватели (из БД А) ───────────────────
    # full_name должен содержать фамилию преподавателя (первое слово)
    # чтобы система могла найти его в расписании
    print("\n[Преподаватели из БД А]")

    teachers = db_a.query(Teacher).all()
    print(f"  Найдено преподавателей в БД А: {len(teachers)}")

    # Создаём учётную запись для нескольких преподавателей как пример
    # Логин = фамилия маленькими буквами, пароль = фамилия + 123
    sample_teachers = teachers[:5]  # первые 5 для примера
    for t in sample_teachers:
        login   = t.surname.lower()
        passwd  = t.surname + "123"
        create_or_update_user(db_b, login, passwd, "teacher", f"{t.surname} {t.name}")

    db_b.commit()

    print("\n" + "=" * 60)
    print("УЧЁТНЫЕ ДАННЫЕ ДЛЯ ВХОДА:")
    print("  Роль admin:            admin        / admin123")
    print("  Роль educational_dept: edu          / edu123")
    print("  Роль student:          student      / student123")
    print()
    for t in sample_teachers:
        print(f"  Роль teacher:          {t.surname.lower():<16} / {t.surname}123")
    print("=" * 60)

    db_a.close()
    db_b.close()


if __name__ == "__main__":
    main()
