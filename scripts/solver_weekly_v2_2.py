"""
НЕДЕЛЬНЫЙ СОЛВЕР РАСПИСАНИЯ v2.2 С СИСТЕМОЙ СМЕН + ФИЗКУЛЬТУРА В СПОРТЗАЛЕ
1-2 курс → 1 смена (слоты 0-4)
3-4 курс → 2 смена (слоты 5-8)
Максимум 15 пар на группу в неделю
+ Учет вычтенных часов из прошедших дней
+ Физкультура только в спортзале
+ Учет отсутствия преподавателей
"""
from ortools.sat.python import cp_model
from datetime import date
import sys
import os
from collections import defaultdict
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocalA, SessionLocalB, init_databases
from app.models import (
    Teacher, StudentGroup, Subject, Classroom,
    GroupSubject, Schedule, CompletedHours, TeacherAbsence
)
from app.config import (
    WORKING_DAYS, SLOTS_PER_DAY, SLOT_TIMES, DAY_NAMES,
    get_semester_for_date, OVERLAPPING_SLOTS, 
    SHIFT_1_SLOTS, SHIFT_2_SLOTS, get_shift_name
)


class WeeklyScheduleSolver:
    """Солвер для генерации недельного расписания с учётом смен по курсам"""
    
    def __init__(self, week_start_date: date):
        """
        Инициализация солвера для конкретной недели
        
        Args:
            week_start_date: Дата начала недели (понедельник)
        """
        self.model = cp_model.CpModel()
        self.week_start_date = week_start_date
        
        # Находим неделю в WORKING_DAYS
        if week_start_date not in WORKING_DAYS:
            raise ValueError(f"Дата {week_start_date} не является рабочим днем")
        
        week_idx = WORKING_DAYS.index(week_start_date)
        
        # Проверяем что это понедельник недели
        if week_start_date.weekday() != 0:
            raise ValueError(f"Дата {week_start_date} не является понедельником")
        
        # Формируем 5 дней недели
        self.week_days = []
        for i in range(5):
            day_idx = week_idx + i
            if day_idx < len(WORKING_DAYS):
                self.week_days.append(WORKING_DAYS[day_idx])
            else:
                break
        
        if len(self.week_days) < 5:
            raise ValueError(f"Неделя с {week_start_date} неполная (только {len(self.week_days)} дней)")
        
        self.week_idx = week_idx // 5
        print(f"\nНеделя: {self.week_days[0]} — {self.week_days[-1]}")
        
        # Определяем семестр для этой недели
        self.semester = get_semester_for_date(self.week_days[0])
        print(f"Семестр: {self.semester}")
        
        # Параметры недели
        self.days_per_week = 5
        self.slots_per_day = SLOTS_PER_DAY  # 9 слотов (2 смены)
        self.slots_per_week = self.days_per_week * self.slots_per_day  # 45
        self.max_pairs_per_group_per_week = 15  # ОГРАНИЧЕНИЕ: максимум 15 пар на группу
        
        # Данные из БД
        self.teachers = {}
        self.groups = {}
        self.subjects = {}
        self.classrooms = []
        self.gym_classrooms = []  # Спортзалы (СЗ1, СЗ2, СЗ3, СЗ4)
        self.regular_classrooms = []  # Обычные кабинеты
        self.assignments = []  # Задания на неделю
        
        # Учет вычтенных часов
        self.completed_hours = {}  # {(group_id, subject_id, teacher_id): hours}
        
        # Отсутствие преподавателей
        self.teacher_absences = set()  # {teacher_id}
        
        # Переменные солвера
        self.schedule_vars = []

    def get_group_shift(self, group_name: str) -> int:
        """
        Определить смену группы по названию
        1-2 курс → 1 смена
        3-4 курс → 2 смена
        """
        parts = group_name.split('-')
        if len(parts) == 2:
            course_code = parts[1][0]  # Первая цифра после дефиса
            course = int(course_code)
            
            if course in [1, 2]:
                return 1  # 1 смена
            elif course in [3, 4]:
                return 2  # 2 смена
        
        return 1  # По умолчанию 1 смена

    def load_completed_hours(self):
        """Загружаем информацию о вычтенных часах из прошедших недель"""
        db_b = SessionLocalB()
        try:
            # Получаем все записи расписания ДО текущей недели
            past_schedules = db_b.query(Schedule).filter(
                Schedule.date < self.week_start_date,
                Schedule.semester == self.semester
            ).all()
            
            # Считаем часы
            hours_dict = defaultdict(int)
            for sched in past_schedules:
                key = (sched.group_id, sched.subject_id, sched.teacher_id)
                hours_dict[key] += 2  # Каждая пара = 2 часа
            
            self.completed_hours = dict(hours_dict)
            
            total_completed = sum(self.completed_hours.values())
            print(f"\n✓ Загружено вычтенных часов: {total_completed} часов")
            print(f"  Уникальных пар (группа+предмет+преподаватель): {len(self.completed_hours)}")
            
        finally:
            db_b.close()

    def load_teacher_absences(self):
        """Загружаем информацию об отсутствующих преподавателях на эту неделю"""
        db_b = SessionLocalB()
        try:
            # Ищем записи об отсутствии, которые пересекаются с нашей неделей
            week_end = self.week_days[-1]
            
            absences = db_b.query(TeacherAbsence).filter(
                TeacherAbsence.absence_start <= week_end,
                TeacherAbsence.absence_end >= self.week_start_date
            ).all()
            
            for absence in absences:
                self.teacher_absences.add(absence.teacher_id)
            
            if self.teacher_absences:
                print(f"\n⚠️ Отсутствующие преподаватели на неделю: {len(self.teacher_absences)}")
                for t_id in self.teacher_absences:
                    if t_id in self.teachers:
                        t = self.teachers[t_id]
                        print(f"  • {t.surname} {t.name}")
            
        finally:
            db_b.close()

    def load_data(self):
        """Загружаем данные из database A и формируем задания на неделю"""
        db = SessionLocalA()
        try:
            # Загружаем справочники
            self.teachers = {t.id: t for t in db.query(Teacher).all()}
            self.groups = {g.id: g for g in db.query(StudentGroup).all()}
            self.subjects = {s.id: s for s in db.query(Subject).all()}
            
            # Разделяем кабинеты на спортзалы и обычные
            all_classrooms = db.query(Classroom).all()
            for c in all_classrooms:
                if c.name.startswith('СЗ'):  # Спортзал
                    self.gym_classrooms.append(c)
                else:
                    self.regular_classrooms.append(c)
            
            self.classrooms = all_classrooms
            
            print(f"\nДанные загружены:")
            print(f"  • Преподавателей: {len(self.teachers)}")
            print(f"  • Групп: {len(self.groups)}")
            print(f"  • Предметов: {len(self.subjects)}")
            print(f"  • Кабинетов: {len(self.classrooms)} (спортзалы: {len(self.gym_classrooms)}, обычные: {len(self.regular_classrooms)})")
            
            # Загружаем вычтенные часы
            self.load_completed_hours()
            
            # Загружаем отсутствие преподавателей
            self.load_teacher_absences()
            
            # Загружаем планы для текущего семестра
            group_subjects = db.query(GroupSubject).filter(
                GroupSubject.semester == self.semester
            ).all()
            
            print(f"  • Учебных планов для семестра {self.semester}: {len(group_subjects)}")
            
            # Недель в семестре
            weeks_in_semester = 16 if self.semester == 1 else 20
            
            # Группируем по группам
            plans_by_group = {}
            for gs in group_subjects:
                plans_by_group.setdefault(gs.group_id, []).append(gs)
            
            # Для каждой группы генерируем МАКСИМУМ 15 пар
            total_pairs = 0
            shift1_pairs = 0
            shift2_pairs = 0
            skipped_absent = 0
            
            for group_id, gs_list in plans_by_group.items():
                group = self.groups[group_id]
                shift = self.get_group_shift(group.name)
                
                # Считаем сколько пар нужно на неделю для каждого предмета
                subject_pairs = []
                for gs in gs_list:
                    # Пропускаем если преподаватель отсутствует
                    if gs.teacher_id in self.teacher_absences:
                        skipped_absent += 1
                        continue
                    
                    hours_per_semester = gs.hours_per_semester
                    
                    # Вычитаем уже вычтенные часы
                    key = (gs.group_id, gs.subject_id, gs.teacher_id)
                    completed = self.completed_hours.get(key, 0)
                    remaining_hours = max(0, hours_per_semester - completed)
                    
                    if remaining_hours < 2:  # Меньше одной пары
                        continue
                    
                    # Считаем пары на неделю
                    pairs_per_semester = remaining_hours // 2
                    pairs_per_week = max(1, pairs_per_semester // weeks_in_semester)
                    
                    subject_pairs.append({
                        'gs': gs,
                        'pairs': pairs_per_week
                    })
                
                # Сортируем по убыванию пар и берём до 15 пар
                subject_pairs.sort(key=lambda x: x['pairs'], reverse=True)
                
                pairs_added = 0
                for sp in subject_pairs:
                    if pairs_added >= self.max_pairs_per_group_per_week:
                        break
                    
                    gs = sp['gs']
                    subject = self.subjects[gs.subject_id]
                    
                    # Добавляем пары, но не больше чем осталось до лимита
                    pairs_to_add = min(sp['pairs'], self.max_pairs_per_group_per_week - pairs_added)
                    
                    for _ in range(pairs_to_add):
                        # Все предметы, включая физкультуру, используют обычные кабинеты
                        is_pe = is_pe = subject.name.strip().lower() == "физическая культура"
                        
                        self.assignments.append({
                            'group': group,
                            'subject': subject,
                            'teacher': self.teachers[gs.teacher_id],
                            'gs_id': gs.id,
                            'shift': shift,
                            'is_pe': is_pe,
                        })
                        pairs_added += 1
                        total_pairs += 1
                        
                        if shift == 1:
                            shift1_pairs += 1
                        else:
                            shift2_pairs += 1
            
            print(f"  • Сформировано пар на неделю: {total_pairs}")
            if skipped_absent > 0:
                print(f"  • Пропущено пар (преподаватель отсутствует): {skipped_absent}")
            
            # Анализ загрузки
            groups_count = len(set(a['group'].id for a in self.assignments))
            shift1_groups = len(set(a['group'].id for a in self.assignments if a['shift'] == 1))
            shift2_groups = len(set(a['group'].id for a in self.assignments if a['shift'] == 2))
            pe_pairs = len([a for a in self.assignments if a['is_pe']])
            
            print(f"\nАнализ загрузки:")
            print(f"  • Групп активных: {groups_count}")
            print(f"    - 1 смена (1-2 курс): {shift1_groups} групп, {shift1_pairs} пар")
            print(f"    - 2 смена (3-4 курс): {shift2_groups} групп, {shift2_pairs} пар")
            print(f"  • Пар физкультуры: {pe_pairs}")
            print(f"  • Пар на группу: максимум {self.max_pairs_per_group_per_week}")
            
        finally:
            db.close()

    def create_variables(self):
        """Создаём переменные для каждого занятия"""
        print("\nСоздание переменных...")
        
        for idx, ass in enumerate(self.assignments):
            # День недели (0-4)
            day = self.model.NewIntVar(0, self.days_per_week - 1, f"day_{idx}")
            
            # Слот в дне (0-8, всего 9 слотов)
            shift = ass['shift']
            if shift == 1:
                slot = self.model.NewIntVar(SHIFT_1_SLOTS[0], SHIFT_1_SLOTS[-1], f"slot_{idx}")
            else:
                slot = self.model.NewIntVar(SHIFT_2_SLOTS[0], SHIFT_2_SLOTS[-1], f"slot_{idx}")
            
            # Абсолютный слот в неделе (0-44)
            slot_in_week = self.model.NewIntVar(0, self.slots_per_week - 1, f"slot_week_{idx}")
            self.model.Add(slot_in_week == day * self.slots_per_day + slot)
            
            # Кабинет - выбираем из правильного списка
            if ass['is_pe']:
                # Физкультура - только спортзалы
                if not self.gym_classrooms:
                    raise ValueError("Нет доступных спортзалов для физкультуры!")
                classroom = self.model.NewIntVar(0, len(self.gym_classrooms) - 1, f"classroom_{idx}")
            else:
                # Обычные предметы - обычные кабинеты
                classroom = self.model.NewIntVar(0, len(self.regular_classrooms) - 1, f"classroom_{idx}")
            
            self.schedule_vars.append({
                'idx': idx,
                'ass': ass,
                'day': day,
                'slot': slot,
                'slot_in_week': slot_in_week,
                'classroom': classroom,
                'shift': shift,
                'is_pe': ass['is_pe'],
            })
        
        print(f"✓ Создано {len(self.schedule_vars)} переменных")

    def add_constraints(self):
        """Добавляем все ограничения"""
        print("\nДобавление ограничений...")
        
        # Группируем занятия
        by_group = {}
        by_teacher = {}
        by_subject_group = {}
        
        for var_dict in self.schedule_vars:
            ass = var_dict['ass']
            g_id = ass['group'].id
            t_id = ass['teacher'].id
            s_id = ass['subject'].id
            
            by_group.setdefault(g_id, []).append(var_dict)
            by_teacher.setdefault(t_id, []).append(var_dict)
            by_subject_group.setdefault((s_id, g_id), []).append(var_dict)
        
        # 1. Группа не может быть в двух местах одновременно
        print("  • Нет пересечений по группам")
        for lessons in by_group.values():
            if len(lessons) > 1:
                slots = [l['slot_in_week'] for l in lessons]
                self.model.AddAllDifferent(slots)
        
        # 2. Преподаватель не может вести два урока одновременно
        print("  • Нет пересечений по преподавателям")
        for lessons in by_teacher.values():
            if len(lessons) > 1:
                slots = [l['slot_in_week'] for l in lessons]
                self.model.AddAllDifferent(slots)
        
        # 3. Пары одного предмета для одной группы - в разных слотах
        print("  • Пары одного предмета в разных слотах")
        for lessons in by_subject_group.values():
            if len(lessons) > 1:
                slots = [l['slot_in_week'] for l in lessons]
                self.model.AddAllDifferent(slots)
        
        # 4. Кабинеты - разделяем на спортзалы и обычные
        print("  • Нет пересечений по кабинетам (с учётом типа)")
        
        # Проверяем спортзалы отдельно
        pe_lessons = [l for l in self.schedule_vars if l['is_pe']]
        if len(pe_lessons) > 1:
            for i in range(len(pe_lessons)):
                for j in range(i + 1, len(pe_lessons)):
                    l1 = pe_lessons[i]
                    l2 = pe_lessons[j]
                    
                    # Если в один слот - разные спортзалы
                    same_slot = self.model.NewBoolVar(f'pe_same_slot_{i}_{j}')
                    self.model.Add(l1['slot_in_week'] == l2['slot_in_week']).OnlyEnforceIf(same_slot)
                    self.model.Add(l1['slot_in_week'] != l2['slot_in_week']).OnlyEnforceIf(same_slot.Not())
                    self.model.Add(l1['classroom'] != l2['classroom']).OnlyEnforceIf(same_slot)
        
        # Проверяем обычные кабинеты
        regular_lessons = [l for l in self.schedule_vars if not l['is_pe']]
        if len(regular_lessons) > 1:
            for i in range(len(regular_lessons)):
                for j in range(i + 1, len(regular_lessons)):
                    l1 = regular_lessons[i]
                    l2 = regular_lessons[j]
                    
                    # Если в один слот - разные кабинеты
                    same_slot = self.model.NewBoolVar(f'reg_same_slot_{i}_{j}')
                    self.model.Add(l1['slot_in_week'] == l2['slot_in_week']).OnlyEnforceIf(same_slot)
                    self.model.Add(l1['slot_in_week'] != l2['slot_in_week']).OnlyEnforceIf(same_slot.Not())
                    self.model.Add(l1['classroom'] != l2['classroom']).OnlyEnforceIf(same_slot)
                    
                    # Пересекающиеся слоты между сменами
                    for slot1, overlapping in OVERLAPPING_SLOTS.items():
                        for slot2 in overlapping:
                            same_day = self.model.NewBoolVar(f'overlap_{i}_{j}_{slot1}_{slot2}')
                            is_slot1 = self.model.NewBoolVar(f'is_slot1_{i}_{j}_{slot1}')
                            is_slot2 = self.model.NewBoolVar(f'is_slot2_{i}_{j}_{slot2}')
                            
                            self.model.Add(l1['day'] == l2['day']).OnlyEnforceIf(same_day)
                            self.model.Add(l1['slot'] == slot1).OnlyEnforceIf(is_slot1)
                            self.model.Add(l2['slot'] == slot2).OnlyEnforceIf(is_slot2)
                            
                            overlap_and_same_day = self.model.NewBoolVar(f'full_overlap_{i}_{j}_{slot1}_{slot2}')
                            self.model.AddBoolAnd([same_day, is_slot1, is_slot2]).OnlyEnforceIf(overlap_and_same_day)
                            
                            self.model.Add(l1['classroom'] != l2['classroom']).OnlyEnforceIf(overlap_and_same_day)
        
        # 5. Максимум пар в день для группы
        print("  • Максимум пар в день для группы")
        for g_id, lessons in by_group.items():
            for day in range(self.days_per_week):
                day_lessons = []
                for l in lessons:
                    is_this_day = self.model.NewBoolVar(f'day_{g_id}_{day}_{l["idx"]}')
                    self.model.Add(l['day'] == day).OnlyEnforceIf(is_this_day)
                    self.model.Add(l['day'] != day).OnlyEnforceIf(is_this_day.Not())
                    day_lessons.append(is_this_day)
                
                shift = lessons[0]['shift']
                max_pairs = 5 if shift == 1 else 4
                self.model.Add(sum(day_lessons) <= max_pairs)
        
        print("✓ Все ограничения добавлены")

    def solve(self, time_limit=300):
        """Запуск солвера"""
        print(f"\nЗапуск солвера (лимит: {time_limit}с)...")
        
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit
        solver.parameters.num_search_workers = 8
        solver.parameters.log_search_progress = True
        
        status = solver.Solve(self.model)
        
        if status == cp_model.OPTIMAL:
            print("\n✓ Найдено ОПТИМАЛЬНОЕ решение!")
            return self.extract_solution(solver)
        elif status == cp_model.FEASIBLE:
            print("\n✓ Найдено ДОПУСТИМОЕ решение!")
            return self.extract_solution(solver)
        else:
            print(f"\n✗ Решение не найдено")
            print(f"Статус: {solver.StatusName(status)}")
            return None

    def extract_solution(self, solver):
        """Извлечение решения"""
        print("\nИзвлечение решения...")
        
        result = []
        for var_dict in self.schedule_vars:
            ass = var_dict['ass']
            day_idx = solver.Value(var_dict['day'])
            slot_idx = solver.Value(var_dict['slot'])
            classroom_idx = solver.Value(var_dict['classroom'])
            
            date_obj = self.week_days[day_idx]
            
            # Выбираем кабинет из правильного списка
            if var_dict['is_pe']:
                classroom = self.gym_classrooms[classroom_idx]
            else:
                classroom = self.regular_classrooms[classroom_idx]
            
            result.append({
                'group_id': ass['group'].id,
                'group_name': ass['group'].name,
                'subject_id': ass['subject'].id,
                'subject_name': ass['subject'].name,
                'teacher_id': ass['teacher'].id,
                'teacher_name': ass['teacher'].name,
                'date': date_obj,
                'day_name': DAY_NAMES[date_obj.weekday()],
                'slot_idx': slot_idx,
                'time': SLOT_TIMES[slot_idx],
                'classroom_id': classroom.id,
                'classroom': classroom.name,
                'semester': self.semester,
                'shift': var_dict['shift'],
            })
        
        result.sort(key=lambda x: (x['date'], x['slot_idx'], x['group_name']))
        
        print(f"✓ Извлечено {len(result)} занятий")
        return result

    def save_to_db(self, data):
        """Сохранение в database B"""
        print(f"\nСохранение в БД B...")
        
        db = SessionLocalB()
        try:
            # Удаляем старое расписание на эти даты
            dates = self.week_days
            db.query(Schedule).filter(Schedule.date.in_(dates)).delete(synchronize_session=False)
            
            # Добавляем новое
            for entry in data:
                schedule = Schedule(
                    group_id=entry['group_id'],
                    group_name=entry['group_name'],
                    subject_id=entry['subject_id'],
                    subject_name=entry['subject_name'],
                    teacher_id=entry['teacher_id'],
                    teacher_name=entry['teacher_name'],
                    date=entry['date'],
                    day_name=entry['day_name'],
                    slot_idx=entry['slot_idx'],
                    time=entry['time'],
                    classroom_id=entry['classroom_id'],
                    classroom=entry['classroom'],
                    semester=entry['semester']
                )
                db.add(schedule)
            
            db.commit()
            print(f"✓ Сохранено {len(data)} записей")
            
        except Exception as e:
            db.rollback()
            print(f"✗ Ошибка: {e}")
            raise
        finally:
            db.close()

    def print_schedule(self, data):
        """Красивый вывод расписания"""
        print("\n" + "=" * 130)
        print(f"РАСПИСАНИЕ НА НЕДЕЛЮ")
        print(f"{self.week_days[0]} — {self.week_days[-1]}")
        print("=" * 130)
        
        current_date = None
        for entry in data:
            if entry['date'] != current_date:
                current_date = entry['date']
                print(f"\n{entry['day_name']}, {entry['date']}")
                print("-" * 130)
            
            shift = get_shift_name(entry['slot_idx'])
            
            print(f"  {entry['time']} │ {shift:8} │ {entry['group_name']:10} │ "
                  f"{entry['subject_name']:45} │ {entry['teacher_name']:30} │ "
                  f"{entry['classroom']:10}")
        
        print("=" * 130)


def generate_weekly_schedule(week_start_date: date, time_limit=300):
    """
    Публичная функция для генерации недельного расписания
    
    Args:
        week_start_date: Дата начала недели (понедельник)
        time_limit: Лимит времени решения в секундах
        
    Returns:
        list: Список записей расписания или None если не найдено решение
    """
    try:
        solver = WeeklyScheduleSolver(week_start_date=week_start_date)
        
        print("\n[1/4] Загрузка данных...")
        solver.load_data()
        
        print("\n[2/4] Создание переменных...")
        solver.create_variables()
        
        print("\n[3/4] Добавление ограничений...")
        solver.add_constraints()
        
        print("\n[4/4] Решение задачи...")
        result = solver.solve(time_limit=time_limit)
        
        if result:
            solver.save_to_db(result)
            solver.print_schedule(result)
            return result
        else:
            print("\n✗ Не удалось найти решение")
            return None
            
    except Exception as e:
        print(f"\n✗ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """Основная функция для тестирования"""
    print("=" * 130)
    print("НЕДЕЛЬНЫЙ СОЛВЕР РАСПИСАНИЯ КОЛЛЕДЖА v2.2")
    print("Учет вычтенных часов + Физкультура в спортзале + Отсутствие преподавателей")
    print("=" * 130)
    
    # Инициализация БД
    print("\nИнициализация баз данных...")
    init_databases()
    print("✓ Базы данных готовы")
    
    # Генерируем расписание на первую неделю
    # Находим первый понедельник учебного года
    first_monday = None
    for day in WORKING_DAYS:
        if day.weekday() == 0:  # Понедельник
            first_monday = day
            break
    
    if first_monday:
        print(f"\nГенерация расписания на неделю с {first_monday}")
        generate_weekly_schedule(first_monday, time_limit=300)
    else:
        print("\n✗ Не найден понедельник в учебном году")


if __name__ == "__main__":
    main()
