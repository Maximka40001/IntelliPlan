"""
ГЕНЕРАТОР УЧЕБНОГО ПЛАНА НА 2 СЕМЕСТР
======================================
Скрипт создаёт записи в таблице group_subjects (semester=2) по аналогии
с планом 1 семестра, корректно сопоставляя предметы через таблицу subjects.

Если для предмета нет дублирующей строки в subjects с semester=2 — скрипт
автоматически создаёт её (с теми же name/hours_per_semester, только semester=2).

Для 4 курса (ИСП-41..44, СА-41..44) во 2 семестре:
  Производственная практика  (id=55) → Дипломное проектирование  (id=57, 120ч)
  Преддипломная практика     (id=56) → Подготовка к защите ВКР   (id=58,  80ч)
  Остальные дисциплины продолжаются как обычно.

Запуск из корня проекта:
  python scripts/create_semester2_plan.py            # вставить в БД
  python scripts/create_semester2_plan.py --dry-run  # только показать
  python scripts/create_semester2_plan.py --force    # пересоздать (удалить старое + вставить)
"""
import sys
import os
import argparse
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

DB_PATH = os.getenv("SQLITE_DB_A", "database_a.db")


def get_db(path=DB_PATH):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_subject_semester2(cur, subj_id_s1, subjects_cache):
    """
    Убеждаемся что предмет с таким же name существует в subjects с semester=2.
    Если нет — создаём. Возвращает id предмета-аналога в семестре 2.
    """
    name_s1, hours_s1, _ = subjects_cache[subj_id_s1]
    key = name_s1.strip().lower()

    # Проверяем кэш
    for sid, (name, hours, sem) in subjects_cache.items():
        if name.strip().lower() == key and sem == 2:
            return sid

    # Создаём запись в subjects
    cur.execute(
        "INSERT INTO subjects (name, hours_per_semester, semester) VALUES (?, ?, 2)",
        (name_s1, hours_s1)
    )
    new_id = cur.lastrowid
    subjects_cache[new_id] = (name_s1, hours_s1, 2)
    return new_id


def main():
    parser = argparse.ArgumentParser(description="Генерация плана 2 семестра")
    parser.add_argument("--dry-run", action="store_true",
                        help="Показать план без записи в БД")
    parser.add_argument("--force", action="store_true",
                        help="Удалить существующий план 2 семестра и создать заново")
    parser.add_argument("--db", default=DB_PATH,
                        help=f"Путь к database_a.db (по умолч.: {DB_PATH})")
    args = parser.parse_args()

    conn = get_db(args.db)
    cur  = conn.cursor()

    # ── Проверяем существующий план 2 семестра ────────────────────────────────
    existing = cur.execute(
        "SELECT COUNT(*) FROM group_subjects WHERE semester=2"
    ).fetchone()[0]

    if existing > 0 and not args.force and not args.dry_run:
        print(f"⚠️  В таблице group_subjects уже есть {existing} записей с semester=2.")
        print("   Используйте --force чтобы пересоздать, или --dry-run для просмотра.")
        conn.close()
        return

    if existing > 0 and args.force and not args.dry_run:
        cur.execute("DELETE FROM group_subjects WHERE semester=2")
        print(f"🗑  Удалено {existing} старых записей semester=2")

    # ── Загружаем справочники ──────────────────────────────────────────────────
    groups   = {r["id"]: r["name"]
                for r in cur.execute("SELECT id, name FROM student_groups").fetchall()}
    teachers = {r["id"]: r["name"]
                for r in cur.execute("SELECT id, name FROM teachers").fetchall()}
    # subjects_cache: id -> (name, hours_per_semester, semester)
    subjects_cache = {r["id"]: (r["name"], r["hours_per_semester"], r["semester"])
                      for r in cur.execute("SELECT id, name, hours_per_semester, semester FROM subjects").fetchall()}

    # ── Строим маппинг name_lower → {sem → id} ────────────────────────────────
    def build_map():
        m = {}
        for sid, (name, hours, sem) in subjects_cache.items():
            key = name.strip().lower()
            if key not in m:
                m[key] = {}
            m[key][sem] = sid
        return m

    # ── Загружаем план 1 семестра ──────────────────────────────────────────────
    sem1_rows = cur.execute("""
        SELECT id, group_id, subject_id, teacher_id, hours_per_semester
        FROM group_subjects
        WHERE semester = 1
        ORDER BY id
    """).fetchall()

    print(f"{'='*70}")
    print(f"ГЕНЕРАТОР ПЛАНА 2 СЕМЕСТРА")
    print(f"{'='*70}")
    print(f"Записей плана 1 семестра: {len(sem1_rows)}")

    # Замены для 4 курса: subject_id_sem1 → (subject_id_sem2, hours)
    REPLACE_4COURSE = {55: (57, 120), 56: (58, 80)}

    to_insert   = []   # финальный список для вставки
    new_subjects = []  # предметы, которые будут созданы в subjects

    for row in sem1_rows:
        group_id   = row["group_id"]
        subj_id_s1 = row["subject_id"]
        teacher_id = row["teacher_id"]
        hours      = row["hours_per_semester"]
        group_name = groups.get(group_id, "")
        course     = int(group_name.split("-")[1][0]) if "-" in group_name else 1

        name_s1, _, _ = subjects_cache[subj_id_s1]

        # ---- 4 курс: специальные замены дисциплин ────────────────────────────
        if course == 4 and subj_id_s1 in REPLACE_4COURSE:
            new_subj_id, new_hours = REPLACE_4COURSE[subj_id_s1]
            new_name = subjects_cache[new_subj_id][0]
            to_insert.append({
                "group_id":           group_id,
                "subject_id":         new_subj_id,
                "teacher_id":         teacher_id,
                "hours_per_semester": new_hours,
                "semester":           2,
                "_group":  group_name,
                "_subject": new_name,
                "_teacher": teachers.get(teacher_id, f"#{teacher_id}"),
                "_note":   f"[4к замена] {name_s1} → {new_name}",
            })
            continue

        # ---- Ищем/создаём аналог предмета в subjects semester=2 ──────────────
        subj_key = name_s1.strip().lower()
        subject_map = build_map()

        if subj_key in subject_map and 2 in subject_map[subj_key]:
            sem2_subj_id = subject_map[subj_key][2]
            note = f"subjects id={sem2_subj_id}"
        else:
            # Создаём новую запись в subjects для семестра 2
            # (только при реальной записи; при dry-run — помечаем)
            new_name_s1, new_hours_s1, _ = subjects_cache[subj_id_s1]
            if args.dry_run:
                sem2_subj_id = f"NEW({name_s1})"
                note = f"⚡ будет создан новый subjects semester=2"
            else:
                cur.execute(
                    "INSERT INTO subjects (name, hours_per_semester, semester) VALUES (?, ?, 2)",
                    (new_name_s1, new_hours_s1)
                )
                sem2_subj_id = cur.lastrowid
                subjects_cache[sem2_subj_id] = (new_name_s1, new_hours_s1, 2)
                note = f"⚡ создан новый subjects id={sem2_subj_id}"
                new_subjects.append((sem2_subj_id, new_name_s1, new_hours_s1))

        to_insert.append({
            "group_id":           group_id,
            "subject_id":         sem2_subj_id if not isinstance(sem2_subj_id, str) else subj_id_s1,
            "teacher_id":         teacher_id,
            "hours_per_semester": hours,
            "semester":           2,
            "_group":   group_name,
            "_subject": name_s1,
            "_teacher": teachers.get(teacher_id, f"#{teacher_id}"),
            "_note":    note,
        })

    # ── Вывод плана ───────────────────────────────────────────────────────────
    print(f"\n{'─'*70}")
    print(f"ПЛАН 2 СЕМЕСТРА ({len(to_insert)} записей)")
    print(f"{'─'*70}")

    current_group = None
    for rec in to_insert:
        if rec["_group"] != current_group:
            current_group = rec["_group"]
            print(f"\n  ▸ {current_group}")
        sid = rec["subject_id"]
        print(
            f"    id={sid!s:5} {rec['_subject']:50s} │ "
            f"{rec['_teacher']:25s} │ {rec['hours_per_semester']:4d}ч │ {rec['_note']}"
        )

    # ── Итоги ─────────────────────────────────────────────────────────────────
    total_hours   = sum(r["hours_per_semester"] for r in to_insert)
    unique_groups = len(set(r["group_id"] for r in to_insert))
    unique_subjs  = len(set(r["subject_id"] for r in to_insert))

    print(f"\n{'─'*70}")
    print(f"Итого записей:  {len(to_insert)}")
    print(f"Групп:          {unique_groups}")
    print(f"Предметов:      {unique_subjs}")
    print(f"Всего часов:    {total_hours}")

    if args.dry_run:
        print(f"\n[dry-run] БД не изменена.")
        conn.close()
        return

    # ── Вставка group_subjects ─────────────────────────────────────────────────
    insert_data = [{k: v for k, v in rec.items() if not k.startswith("_")}
                   for rec in to_insert]

    cur.executemany("""
        INSERT INTO group_subjects (group_id, subject_id, teacher_id, hours_per_semester, semester)
        VALUES (:group_id, :subject_id, :teacher_id, :hours_per_semester, :semester)
    """, insert_data)

    conn.commit()

    inserted = cur.execute(
        "SELECT COUNT(*) FROM group_subjects WHERE semester=2"
    ).fetchone()[0]

    print(f"\n✅ Вставлено {inserted} записей в group_subjects (semester=2)")
    if new_subjects:
        print(f"✅ Добавлено {len(new_subjects)} новых предметов в subjects (semester=2):")
        for sid, name, hrs in new_subjects:
            print(f"   id={sid} '{name}' {hrs}ч")
    print(f"\n   Файл БД: {os.path.abspath(args.db)}")
    conn.close()


if __name__ == "__main__":
    main()
