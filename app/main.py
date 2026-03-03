"""
FastAPI application main file с интеграцией AI чата и системой аутентификации
"""
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel
from datetime import datetime, date, timedelta
import sys, os, hashlib
from starlette.middleware.sessions import SessionMiddleware

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_db_a, get_db_b, init_databases
from app.models import (Schedule, CompletedHours, TeacherAbsence,
                        Teacher, StudentGroup, Subject, GroupSubject, User)
from app.config import (DAY_NAMES, SLOT_TIMES, get_date_info, WORKING_DAYS,
                        SEMESTER_1_MONDAYS, SEMESTER_2_MONDAYS)

import ai_handler
from scripts.solver_weekly_v2_2 import generate_weekly_schedule

app = FastAPI(title="IntelliPlan")

app.add_middleware(SessionMiddleware, secret_key="intelliplan-secret-key-2025-stable")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


# ─── Startup ──────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    init_databases()
    create_default_users()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def create_default_users():
    from app.database import SessionLocalB
    db = SessionLocalB()
    try:
        existing = db.query(User).first()
        if existing:
            return
        users = [
            User(username="admin",   password_hash=hash_password("admin123"),
                 role="admin",            full_name="Администратор"),
            User(username="teacher", password_hash=hash_password("teacher123"),
                 role="educational_dept", full_name="Учебная часть"),
            User(username="student", password_hash=hash_password("student123"),
                 role="student",          full_name="Студент"),
        ]
        db.add_all(users)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Ошибка создания пользователей: {e}")
    finally:
        db.close()


# ─── Roles ────────────────────────────────────────────────────────────────────
# admin           — полный доступ
# educational_dept — генерация, просмотр, AI-чат
# teacher         — своё расписание + свои часы (только чтение)
# student         — расписание всех групп (только чтение)

def get_current_user(request: Request, db: Session = Depends(get_db_b)) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return user


# ─── Pydantic ─────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

class ChatMessage(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: dict
    success: bool

class RegenerateRequest(BaseModel):
    week_start_date: str


# ─── Pages ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request,
                    user: User = Depends(get_current_user),
                    db_a: Session = Depends(get_db_a),
                    db_b: Session = Depends(get_db_b)):

    # Для teacher — ищем его фамилию в расписании чтобы знать его имя
    teacher_filter = None
    if user.role == "teacher":
        # username совпадает с фамилией или full_name = "Фамилия И.О."
        # Ищем по full_name (первое слово = фамилия) или по username
        teacher_filter = user.full_name or user.username

    # Расписание
    q = db_b.query(Schedule).order_by(Schedule.date, Schedule.slot_idx, Schedule.group_name)
    if user.role == "teacher" and teacher_filter:
        q = q.filter(Schedule.teacher_name.ilike(f"%{teacher_filter.split()[0]}%"))

    schedule_items_orm = q.all()
    schedule_items = [{
        "group_name":   i.group_name,
        "subject_name": i.subject_name,
        "teacher_name": i.teacher_name,
        "date":         i.date.strftime("%Y-%m-%d"),
        "day_name":     i.day_name,
        "slot_idx":     i.slot_idx,
        "time":         i.time,
        "classroom":    i.classroom,
        "semester":     i.semester,
    } for i in schedule_items_orm]

    groups        = sorted(list(set(i["group_name"]   for i in schedule_items)))
    teachers_list = sorted(list(set(i["teacher_name"] for i in schedule_items)))

    total_lessons  = len(schedule_items)
    total_groups   = len(groups)
    total_teachers = len(teachers_list)
    total_subjects = len(set(i["subject_name"] for i in schedule_items))

    # Понедельники обоих семестров для генерации
    s1 = [(m.strftime("%Y-%m-%d"),
           f"1 сем. — неделя с {m.strftime('%d.%m.%Y')}") for m in SEMESTER_1_MONDAYS]
    s2 = [(m.strftime("%Y-%m-%d"),
           f"2 сем. — неделя с {m.strftime('%d.%m.%Y')}") for m in SEMESTER_2_MONDAYS]
    available_mondays = s1 + s2   # список (value, label)

    role_display = {
        "admin":            "Администратор",
        "educational_dept": "Учебная часть",
        "teacher":          "Преподаватель",
        "student":          "Студент",
    }.get(user.role, user.role)

    today = date.today()
    pending_absences = 0
    if user.role in ["admin", "educational_dept"]:
        pending_absences = db_b.query(TeacherAbsence).filter(
            TeacherAbsence.absence_end >= today,
            TeacherAbsence.processed == False
        ).count()

    return templates.TemplateResponse("dashboard.html", {
        "request":          request,
        "schedule_items":   schedule_items,
        "groups":           groups,
        "teachers_list":    teachers_list,
        "total_lessons":    total_lessons,
        "total_groups":     total_groups,
        "total_teachers":   total_teachers,
        "total_subjects":   total_subjects,
        "available_mondays": available_mondays,
        "user_role":        user.role,
        "user_role_display": role_display,
        "username":         user.full_name or user.username,
        "today":            today.strftime("%Y-%m-%d"),
        "pending_absences": pending_absences,
        "teacher_filter":   teacher_filter or "",
    })


# ─── Auth ─────────────────────────────────────────────────────────────────────

@app.post("/api/login")
async def login(request: Request, login_data: LoginRequest,
                db: Session = Depends(get_db_b)):
    user = db.query(User).filter(User.username == login_data.username).first()
    if not user or user.password_hash != hash_password(login_data.password):
        return JSONResponse(
            content={"success": False, "message": "Неверный логин или пароль"},
            status_code=401)
    request.session["user_id"] = user.id
    request.session["username"] = user.username
    request.session["role"] = user.role
    return {"success": True}


@app.post("/api/logout")
async def logout(request: Request):
    request.session.clear()
    return {"success": True}


# ─── Schedule API ──────────────────────────────────────────────────────────────

@app.get("/api/schedule")
async def get_schedule(
    group:     Optional[str] = None,
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
    teacher:   Optional[str] = None,
    user: User = Depends(get_current_user),
    db:   Session = Depends(get_db_b)
):
    q = db.query(Schedule)

    # Для роли teacher — автоматически фильтруем по его фамилии
    if user.role == "teacher":
        surname = (user.full_name or user.username).split()[0]
        q = q.filter(Schedule.teacher_name.ilike(f"%{surname}%"))
    else:
        if teacher and teacher != "all":
            q = q.filter(Schedule.teacher_name == teacher)
        if group and group != "all":
            q = q.filter(Schedule.group_name == group)

    if date_from:
        try: q = q.filter(Schedule.date >= datetime.strptime(date_from, "%Y-%m-%d").date())
        except: pass
    if date_to:
        try: q = q.filter(Schedule.date <= datetime.strptime(date_to, "%Y-%m-%d").date())
        except: pass

    items = q.order_by(Schedule.date, Schedule.slot_idx, Schedule.group_name).all()
    return [{
        "group_name": i.group_name, "subject_name": i.subject_name,
        "teacher_name": i.teacher_name, "date": i.date.strftime("%Y-%m-%d"),
        "day_name": i.day_name, "slot_idx": i.slot_idx,
        "time": i.time, "classroom": i.classroom, "semester": i.semester
    } for i in items]


@app.get("/api/stats")
async def get_stats(user: User = Depends(get_current_user), db: Session = Depends(get_db_b)):
    items = db.query(Schedule).all()
    if not items:
        return {"total_lessons": 0, "total_groups": 0, "total_teachers": 0,
                "total_subjects": 0, "group_stats": [], "teacher_stats": []}
    groups, teachers = {}, {}
    for i in items:
        groups[i.group_name] = groups.get(i.group_name, 0) + 1
        teachers[i.teacher_name] = teachers.get(i.teacher_name, 0) + 1
    return {
        "total_lessons": len(items), "total_groups": len(groups),
        "total_teachers": len(teachers),
        "total_subjects": len(set(i.subject_name for i in items)),
        "group_stats":   [{"name": k, "lessons": v} for k, v in sorted(groups.items())],
        "teacher_stats": [{"name": k, "lessons": v} for k, v in sorted(teachers.items())]
    }


# ─── Teacher Hours API  (ПРАВИЛЬНАЯ ЛОГИКА) ────────────────────────────────────
#
# ПЛАН   = group_subjects.hours_per_semester  из БД А  (учебный план)
# ФАКТ   = COUNT(занятия в расписании с date <= today) * 2  из БД Б
# ИТОГО  = все занятия в расписании * 2  (запланировано в расписании)
#
# Это исправляет баг «100% везде» — раньше план брался тоже из расписания.
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/teacher-hours")
async def get_teacher_hours(
    teacher_name: Optional[str] = None,
    user: User = Depends(get_current_user),
    db_a: Session = Depends(get_db_a),
    db_b: Session = Depends(get_db_b)
):
    # Для роли teacher — только свои данные
    if user.role == "teacher":
        teacher_name = (user.full_name or user.username).split()[0]

    today = date.today()

    # Получаем план из group_subjects (БД А)
    plan_rows = db_a.query(GroupSubject).all()
    teachers_map  = {t.id: t for t in db_a.query(Teacher).all()}
    groups_map    = {g.id: g.name for g in db_a.query(StudentGroup).all()}
    subjects_map  = {s.id: s.name for s in db_a.query(Subject).all()}

    # Строим словарь: teacher_name -> subject_name -> plan_hours
    from collections import defaultdict
    plan: dict = defaultdict(lambda: defaultdict(int))
    for p in plan_rows:
        t = teachers_map.get(p.teacher_id)
        if not t:
            continue
        tname = t.name   # полное имя вида "Русанов И.Д."
        sname = subjects_map.get(p.subject_id, "")
        plan[tname][sname] += p.hours_per_semester

    # Если фильтр по имени — оставляем только подходящего
    if teacher_name and teacher_name != "all":
        plan = {k: v for k, v in plan.items()
                if teacher_name.lower() in k.lower()}

    # Считаем выполненные и запланированные часы из расписания (БД Б)
    # Запланировано в расписании = все занятия * 2
    # Выполнено = занятия с date <= today * 2
    result = []
    for tname, subjects_plan in sorted(plan.items()):
        rows = []
        total_plan = total_sched = total_done = 0

        for sname, plan_hrs in sorted(subjects_plan.items()):
            # Занятия в расписании всего
            sched_total = db_b.query(Schedule).filter(
                Schedule.teacher_name.ilike(f"%{tname.split()[0]}%"),
                Schedule.subject_name == sname
            ).count() * 2

            # Занятия выполненные (прошедшие)
            sched_done = db_b.query(Schedule).filter(
                Schedule.teacher_name.ilike(f"%{tname.split()[0]}%"),
                Schedule.subject_name == sname,
                Schedule.date <= today
            ).count() * 2

            rows.append({
                "subject":           sname,
                "plan_hours":        plan_hrs,
                "scheduled_hours":   sched_total,
                "completed_hours":   sched_done,
                "remaining_plan":    max(0, plan_hrs - sched_done),
            })
            total_plan  += plan_hrs
            total_sched += sched_total
            total_done  += sched_done

        result.append({
            "teacher_name":    tname,
            "subjects":        rows,
            "total_plan":      total_plan,
            "total_scheduled": total_sched,
            "total_completed": total_done,
            "total_remaining": max(0, total_plan - total_done),
        })

    return result


# ─── Group Hours API  (ПРАВИЛЬНАЯ ЛОГИКА) ─────────────────────────────────────

@app.get("/api/group-hours")
async def get_group_hours(
    group_name: Optional[str] = None,
    user: User = Depends(get_current_user),
    db_a: Session = Depends(get_db_a),
    db_b: Session = Depends(get_db_b)
):
    today = date.today()

    plan_rows    = db_a.query(GroupSubject).all()
    teachers_map = {t.id: t.name for t in db_a.query(Teacher).all()}
    groups_map   = {g.id: g.name for g in db_a.query(StudentGroup).all()}
    subjects_map = {s.id: s.name for s in db_a.query(Subject).all()}

    from collections import defaultdict
    plan: dict = defaultdict(lambda: defaultdict(int))
    for p in plan_rows:
        gname = groups_map.get(p.group_id, "")
        sname = subjects_map.get(p.subject_id, "")
        plan[gname][sname] += p.hours_per_semester

    if group_name and group_name != "all":
        plan = {k: v for k, v in plan.items() if k == group_name}

    result = []
    for gname, subjects_plan in sorted(plan.items()):
        rows = []
        total_plan = total_sched = total_done = 0

        for sname, plan_hrs in sorted(subjects_plan.items()):
            sched_total = db_b.query(Schedule).filter(
                Schedule.group_name == gname,
                Schedule.subject_name == sname
            ).count() * 2

            sched_done = db_b.query(Schedule).filter(
                Schedule.group_name == gname,
                Schedule.subject_name == sname,
                Schedule.date <= today
            ).count() * 2

            rows.append({
                "subject":         sname,
                "plan_hours":      plan_hrs,
                "scheduled_hours": sched_total,
                "completed_hours": sched_done,
                "remaining_plan":  max(0, plan_hrs - sched_done),
            })
            total_plan  += plan_hrs
            total_sched += sched_total
            total_done  += sched_done

        result.append({
            "group_name":      gname,
            "subjects":        rows,
            "total_plan":      total_plan,
            "total_scheduled": total_sched,
            "total_completed": total_done,
            "total_remaining": max(0, total_plan - total_done),
        })

    return result


# ─── Disciplines (Admin) ───────────────────────────────────────────────────────

@app.get("/api/remaining-discipline-hours")
async def get_remaining_discipline_hours(
    user: User = Depends(get_current_user),
    db_a: Session = Depends(get_db_a),
    db_b: Session = Depends(get_db_b)
):
    if user.role != "admin":
        return JSONResponse(content={"success": False, "message": "Доступ запрещён"}, status_code=403)

    today        = date.today()
    plan_items   = db_a.query(GroupSubject).all()
    teachers_map = {t.id: t.name for t in db_a.query(Teacher).all()}
    groups_map   = {g.id: g.name for g in db_a.query(StudentGroup).all()}
    subjects_map = {s.id: s.name for s in db_a.query(Subject).all()}

    result = []
    for p in plan_items:
        gname = groups_map.get(p.group_id, f"Группа {p.group_id}")
        sname = subjects_map.get(p.subject_id, f"Предмет {p.subject_id}")
        tname = teachers_map.get(p.teacher_id, f"Преп. {p.teacher_id}")

        completed = db_b.query(Schedule).filter(
            Schedule.group_name == gname,
            Schedule.subject_name == sname,
            Schedule.date <= today
        ).count() * 2

        scheduled = db_b.query(Schedule).filter(
            Schedule.group_name == gname,
            Schedule.subject_name == sname
        ).count() * 2

        result.append({
            "group":            gname,
            "subject":          sname,
            "teacher":          tname,
            "semester":         p.semester,
            "plan_hours":       p.hours_per_semester,
            "scheduled_hours":  scheduled,
            "completed_hours":  min(completed, p.hours_per_semester),
            "remaining_hours":  max(0, p.hours_per_semester - completed),
            "pct": round(min(100, completed / p.hours_per_semester * 100)
                         if p.hours_per_semester else 0)
        })

    return sorted(result, key=lambda x: (x["group"], x["subject"]))


# ─── Chat / AI ────────────────────────────────────────────────────────────────

@app.post("/api/chat")
async def chat_with_ai(
    message: ChatMessage,
    request: Request,
    user: User = Depends(get_current_user),
    db_a: Session = Depends(get_db_a),
    db_b: Session = Depends(get_db_b)
):
    # Только admin и educational_dept имеют доступ к AI чату
    if user.role not in ["admin", "educational_dept"]:
        return ChatResponse(response={
            "success": False,
            "message": "Нет прав доступа к AI помощнику.",
            "action": "error"
        }, success=False)

    msg = message.message.strip()

    # ── /absence ──────────────────────────────────────────────────────────────
    if msg.startswith("/absence"):
        import re
        m = re.search(
            r'/absence\s+(\S+)\s+с?\s*(\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?)\s+по\s+(\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?)\s*(.*)?',
            msg, re.IGNORECASE)
        if not m:
            return ChatResponse(response={
                "success": False,
                "message": "Формат: /absence Фамилия с ДД.ММ по ДД.ММ [причина]\n"
                           "Пример: /absence Иванов с 01.03 по 05.03 болезнь",
                "action": "hint"
            }, success=False)

        surname, d1, d2, reason_raw = m.group(1), m.group(2), m.group(3), m.group(4)
        reason = reason_raw.strip() if reason_raw else "Не указана"

        def parse_date(s):
            import re as _re
            parts = _re.split(r'[./]', s)
            day, month = int(parts[0]), int(parts[1])
            yr = int(parts[2]) if len(parts) > 2 else date.today().year
            if yr < 100: yr += 2000
            return date(yr, month, day)

        try:
            abs_start, abs_end = parse_date(d1), parse_date(d2)
        except Exception as e:
            return ChatResponse(response={
                "success": False, "message": f"Ошибка разбора дат: {e}", "action": "error"
            }, success=False)

        teacher = db_a.query(Teacher).filter(Teacher.surname.ilike(f"%{surname}%")).first()
        if not teacher:
            return ChatResponse(response={
                "success": False,
                "message": f"Преподаватель с фамилией '{surname}' не найден в БД.",
                "action": "error"
            }, success=False)

        pending = request.session.get("pending_absences", [])
        pending.append({
            "teacher_id":      teacher.id,
            "teacher_surname": teacher.surname,
            "teacher_name":    f"{teacher.surname} {teacher.name}",
            "absence_start":   abs_start.isoformat(),
            "absence_end":     abs_end.isoformat(),
            "reason":          reason,
        })
        request.session["pending_absences"] = pending

        return ChatResponse(response={
            "success": True,
            "message": (f"✅ Добавлено в очередь:\n"
                        f"👤 {teacher.surname} {teacher.name}\n"
                        f"📅 {abs_start.strftime('%d.%m.%Y')} — {abs_end.strftime('%d.%m.%Y')}\n"
                        f"📝 Причина: {reason}\n\n"
                        f"Используйте /generate для применения и пересчёта расписания."),
            "action":        "absence_queued",
            "pending_count": len(pending)
        }, success=True)

    # ── /generate ─────────────────────────────────────────────────────────────
    if msg.startswith("/generate"):
        pending = request.session.get("pending_absences", [])
        if not pending:
            return ChatResponse(response={
                "success": True,
                "message": "ℹ️ Очередь пуста. Добавьте отсутствия через /absence.",
                "action": "no_action"
            }, success=True)

        saved = 0
        affected_weeks: set = set()
        for absence in pending:
            try:
                s = date.fromisoformat(absence["absence_start"])
                e = date.fromisoformat(absence["absence_end"])
                db_b.add(TeacherAbsence(
                    teacher_id=absence["teacher_id"],
                    teacher_surname=absence["teacher_surname"],
                    absence_start=s, absence_end=e,
                    reason=absence.get("reason"), processed=False))
                cur = s
                while cur <= e:
                    mon = cur - timedelta(days=cur.weekday())
                    if mon in WORKING_DAYS:
                        affected_weeks.add(mon)
                    cur += timedelta(days=7)
                saved += 1
            except Exception as ex:
                print(f"Ошибка сохранения: {ex}")
        db_b.commit()
        request.session["pending_absences"] = []

        if not affected_weeks:
            return ChatResponse(response={
                "success": True,
                "message": "ℹ️ Нет рабочих недель для регенерации.",
                "action": "no_action"
            }, success=True)

        weeks = sorted(affected_weeks)
        txt = f"📋 Сохранено: {saved} отсутствие(й)\n🗓 Недель к регенерации: {len(weeks)}\n\n"
        for mon in weeks[:3]:
            try:
                res = generate_weekly_schedule(mon, time_limit=120)
                txt += (f"✅ {mon.strftime('%d.%m')}: {len(res)} пар\n" if res
                        else f"⚠️ {mon.strftime('%d.%m')}: решение не найдено\n")
            except Exception as ex:
                txt += f"❌ {mon.strftime('%d.%m')}: {ex}\n"
        if len(weeks) > 3:
            txt += f"\n⚠️ Ещё {len(weeks)-3} недель — перегенерируйте вручную."

        return ChatResponse(response={
            "success": True, "message": txt,
            "action": "schedule_regenerated", "regenerated": True
        }, success=True)

    # ── /status ───────────────────────────────────────────────────────────────
    if msg.startswith("/status"):
        pending = request.session.get("pending_absences", [])
        if not pending:
            txt = "📭 Очередь пуста."
        else:
            txt = f"📬 В очереди {len(pending)} запись(ей):\n\n"
            for i, a in enumerate(pending, 1):
                txt += (f"{i}. {a['teacher_name']}\n"
                        f"   {a['absence_start']} → {a['absence_end']}\n"
                        f"   Причина: {a['reason']}\n\n")
            txt += "Используйте /generate для применения."
        return ChatResponse(response={"success": True, "message": txt, "action": "status"}, success=True)

    # ── /clear ────────────────────────────────────────────────────────────────
    if msg.startswith("/clear"):
        request.session["pending_absences"] = []
        return ChatResponse(response={
            "success": True, "message": "🗑️ Очередь очищена.", "action": "cleared"
        }, success=True)

    # ── /help ─────────────────────────────────────────────────────────────────
    if msg.startswith("/help") or msg == "":
        return ChatResponse(response={
            "success": True,
            "message": ("📖 Команды AI помощника:\n\n"
                        "/absence Фамилия с ДД.ММ по ДД.ММ [причина]\n"
                        "   → Добавить отсутствие в очередь\n\n"
                        "/generate\n"
                        "   → Сохранить очередь в БД и пересчитать расписание\n\n"
                        "/status   → Показать очередь\n"
                        "/clear    → Очистить очередь\n"
                        "/help     → Эта справка"),
            "action": "help"
        }, success=True)

    # ── Свободный текст ───────────────────────────────────────────────────────
    try:
        ai_response = ai_handler.process_ai_request(msg)
        return ChatResponse(response=ai_response, success=ai_response.get("success", False))
    except Exception as e:
        return ChatResponse(response={
            "success": False,
            "message": f"Команда не распознана. Введите /help для справки.",
            "action": "unknown"
        }, success=False)


# ─── Generate / Delete ────────────────────────────────────────────────────────

@app.post("/api/regenerate-week")
async def regenerate_week(req: RegenerateRequest, user: User = Depends(get_current_user)):
    if user.role not in ["admin", "educational_dept"]:
        return JSONResponse(content={"success": False, "message": "Нет прав"}, status_code=403)
    try:
        week_start = datetime.strptime(req.week_start_date, "%Y-%m-%d").date()
        if week_start.weekday() != 0:
            return JSONResponse(content={"success": False,
                                         "message": "Дата не является понедельником"}, status_code=400)
        result = generate_weekly_schedule(week_start, time_limit=180)
        if result:
            return {"success": True,
                    "message": f"Расписание с {week_start.strftime('%d.%m.%Y')} сгенерировано",
                    "lessons_count": len(result)}
        return JSONResponse(content={"success": False, "message": "Решение не найдено"}, status_code=500)
    except Exception as e:
        return JSONResponse(content={"success": False, "message": str(e)}, status_code=500)


@app.delete("/api/delete-schedule")
async def delete_schedule(user: User = Depends(get_current_user), db: Session = Depends(get_db_b)):
    if user.role != "admin":
        return JSONResponse(content={"success": False, "message": "Нет прав"}, status_code=403)
    try:
        count = db.query(Schedule).delete()
        db.commit()
        return {"success": True, "message": f"Удалено {count} записей"}
    except Exception as e:
        db.rollback()
        return JSONResponse(content={"success": False, "message": str(e)}, status_code=500)


@app.get("/api/teacher-absences")
async def get_teacher_absences(user: User = Depends(get_current_user), db: Session = Depends(get_db_b)):
    if user.role not in ["admin", "educational_dept"]:
        return JSONResponse(content={"success": False, "message": "Нет прав"}, status_code=403)
    today = date.today()
    absences = db.query(TeacherAbsence).filter(
        TeacherAbsence.absence_end >= today
    ).order_by(TeacherAbsence.absence_start).all()
    return [{
        "id": a.id, "teacher_id": a.teacher_id, "teacher_surname": a.teacher_surname,
        "absence_start": a.absence_start.strftime("%Y-%m-%d"),
        "absence_end":   a.absence_end.strftime("%Y-%m-%d"),
        "reason": a.reason, "processed": a.processed
    } for a in absences]


# ─── Teacher profile API (для роли teacher) ────────────────────────────────────

@app.get("/api/my-schedule")
async def my_schedule(user: User = Depends(get_current_user), db: Session = Depends(get_db_b)):
    """Своё расписание для преподавателя"""
    if user.role != "teacher":
        return JSONResponse(content={"success": False, "message": "Только для роли teacher"}, status_code=403)
    surname = (user.full_name or user.username).split()[0]
    items = db.query(Schedule).filter(
        Schedule.teacher_name.ilike(f"%{surname}%")
    ).order_by(Schedule.date, Schedule.slot_idx).all()
    return [{"group_name": i.group_name, "subject_name": i.subject_name,
             "date": i.date.strftime("%Y-%m-%d"), "day_name": i.day_name,
             "slot_idx": i.slot_idx, "time": i.time, "classroom": i.classroom} for i in items]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
