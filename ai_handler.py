"""
AI модуль - обёртка для process_ai_request
При отсутствии Groq-ключа или ошибке возвращает подсказку с командами.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def process_ai_request(user_message: str) -> dict:
    """
    Пытается обработать свободный текст через real_ai.
    Если real_ai недоступен — возвращает подсказку.
    """
    try:
        from real_ai import extract_absence_info
        from app.database import SessionLocalA, SessionLocalB
        from app.models import Teacher, TeacherAbsence
        from app.config import WORKING_DAYS
        from datetime import date, timedelta
        from scripts.solver_weekly_v2_2 import generate_weekly_schedule

        # Проверяем ключевые слова
        keywords = ['не сможет', 'болеет', 'отпуск', 'отсутствует', 'не выйдет', 'болен', 'не придет']
        if not any(kw in user_message.lower() for kw in keywords):
            return {
                "success": False,
                "message": ("Используйте команды:\n"
                            "/absence Фамилия с ДД.ММ по ДД.ММ [причина]\n"
                            "/generate  — применить очередь\n"
                            "/status    — показать очередь\n"
                            "/help      — справка"),
                "action": "hint"
            }

        ai_result = extract_absence_info(user_message)
        teacher_surname = ai_result.get("teacher_surname")
        absence_dates   = ai_result.get("absence_dates", [])

        if not teacher_surname or not absence_dates:
            return {
                "success": False,
                "message": "Не удалось распознать данные. Используйте /absence для точного ввода.",
                "action": "error"
            }

        db_a = SessionLocalA()
        teacher = db_a.query(Teacher).filter(Teacher.surname.ilike(f"%{teacher_surname}%")).first()
        db_a.close()

        if not teacher:
            return {"success": False,
                    "message": f"Преподаватель '{teacher_surname}' не найден.",
                    "action": "error"}

        from datetime import date as date_cls
        today = date_cls.today()
        parsed = []
        for ds in absence_dates:
            try:
                if '.' in ds:
                    d, m = map(int, ds.split('.'))
                    parsed.append(date_cls(today.year, m, d))
                else:
                    parsed.append(date_cls(today.year, today.month, int(ds)))
            except: pass

        if not parsed:
            return {"success": False, "message": "Не удалось распарсить даты.", "action": "error"}

        parsed.sort()
        start, end = parsed[0], parsed[-1]

        return {
            "success": True,
            "message": (f"✅ Распознано: {teacher.surname} {teacher.name}\n"
                        f"📅 {start.strftime('%d.%m.%Y')} — {end.strftime('%d.%m.%Y')}\n\n"
                        f"Используйте /generate для применения изменений."),
            "action": "absence_detected",
            "data": {
                "teacher_id": teacher.id,
                "teacher_surname": teacher.surname,
                "absence_start": start.isoformat(),
                "absence_end": end.isoformat()
            }
        }

    except ImportError:
        return {
            "success": False,
            "message": ("⚠️ Модуль real_ai недоступен (нет API-ключа или пакета groq).\n\n"
                        "Используйте команды напрямую:\n"
                        "/absence Фамилия с ДД.ММ по ДД.ММ [причина]\n"
                        "/generate — применить очередь\n"
                        "/help — справка"),
            "action": "hint"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Ошибка: {str(e)}\n\nИспользуйте /help для справки.",
            "action": "error"
        }
