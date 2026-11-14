from datetime import date, datetime, time, timedelta

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from . import services
from .models import CustomUser, Habit, HabitRecord, PeriodBonus, Progress

# Referencia de calendario (2026): lunes 2-nov. Semana S0 = 2-8 nov.
MONDAY = date(2026, 11, 2)
TUESDAY = date(2026, 11, 3)
WEDNESDAY = date(2026, 11, 4)
THURSDAY = date(2026, 11, 5)


class XpForCompletedDayRuleTests(SimpleTestCase):
  """Regla B (pura): en semanales y mensuales solo dan XP los días hasta la meta."""

  def test_daily_always_gives_xp(self):
    for days_before in [0, 1, 7]:
      with self.subTest(days_before=days_before):
        self.assertEqual(services.xp_for_completed_day("daily", 1, days_before), (25, 20))

  def test_weekly_gives_xp_only_up_to_the_target(self):
    for days_before, expected in [(0, (25, 20)), (1, (25, 20)), (2, (25, 20)),
                                  (3, (0, 0)), (4, (0, 0)), (6, (0, 0))]:
      with self.subTest(days_before=days_before):
        self.assertEqual(services.xp_for_completed_day("weekly", 3, days_before), expected)

  def test_monthly_gives_xp_only_up_to_the_target(self):
    self.assertEqual(services.xp_for_completed_day("monthly", 2, 1), (25, 20))
    self.assertEqual(services.xp_for_completed_day("monthly", 2, 2), (0, 0))

  def test_missing_target_is_treated_as_one(self):
    self.assertEqual(services.xp_for_completed_day("weekly", None, 0), (25, 20))
    self.assertEqual(services.xp_for_completed_day("weekly", None, 1), (0, 0))

  def test_record_xp_in_a_period_is_capped_by_the_target(self):
    # Completando TODOS los días del periodo, el XP de registros nunca pasa de meta × 25
    week = sum(services.xp_for_completed_day("weekly", 5, n)[0] for n in range(7))
    month = sum(services.xp_for_completed_day("monthly", 28, n)[0] for n in range(31))
    self.assertEqual(week, 5 * 25)
    self.assertEqual(month, 28 * 25)


def make_record(habit, day, completed=True):
  return HabitRecord.objects.create(
    habit=habit,
    user=habit.user,
    date=timezone.make_aware(datetime.combine(day, time(0, 0))),
    completed=completed,
  )


class SetDayCompletedTests(TestCase):
  def setUp(self):
    self.user = CustomUser.objects.create_user(username="ana", password="Ana#Segura2026")
    self.daily = Habit.objects.create(user=self.user, name="Leer")
    self.weekly = Habit.objects.create(
      user=self.user, name="Gimnasio", frequency="weekly", target_per_period=3
    )

  def _complete(self, habit, day):
    """Completa un día por el camino real (con ledger y bonus), como hará la vista."""
    record = make_record(habit, day, completed=False)
    return services.set_day_completed(habit, record, True, today=day)

  def _xp(self, habit):
    habit_progress = Progress.objects.filter(user=self.user, habit=habit).first()
    global_progress = Progress.objects.filter(user=self.user, habit=None).first()
    return (
      (habit_progress.level, habit_progress.experience) if habit_progress else (1, 0),
      (global_progress.level, global_progress.experience) if global_progress else (1, 0),
    )

  # --- diarios ---
  def test_completing_a_daily_gives_xp_and_stores_it_in_the_record(self):
    record = make_record(self.daily, THURSDAY, completed=False)

    result = services.set_day_completed(self.daily, record, True, today=THURSDAY)

    self.assertEqual(result, services.CompletionResult(True, 25, 20, services.NO_CHANGE))
    record.refresh_from_db()
    self.assertEqual((record.completed, record.xp_habit, record.xp_global), (True, 25, 20))
    self.assertIsNotNone(record.completed_at)
    self.assertEqual(self._xp(self.daily), ((1, 25), (1, 20)))

  def test_uncompleting_gives_back_exactly_what_was_stored(self):
    # A 10 XP de subir de nivel: completar cruza el nivel y desmarcar debe volver a bajar
    Progress.objects.create(user=self.user, habit=self.daily, level=1, experience=90)
    Progress.objects.create(user=self.user, habit=None, level=1, experience=90)
    record = make_record(self.daily, THURSDAY, completed=False)

    services.set_day_completed(self.daily, record, True, today=THURSDAY)
    self.assertEqual(self._xp(self.daily), ((2, 15), (2, 10)))
    result = services.set_day_completed(self.daily, record, False, today=THURSDAY)

    self.assertEqual(result, services.CompletionResult(True, -25, -20, services.NO_CHANGE))
    self.assertEqual(self._xp(self.daily), ((1, 90), (1, 90)))
    record.refresh_from_db()
    self.assertEqual((record.completed, record.xp_habit, record.xp_global), (False, 0, 0))
    self.assertIsNone(record.completed_at)

  def test_setting_the_same_state_twice_changes_nothing(self):
    record = make_record(self.daily, THURSDAY, completed=False)

    services.set_day_completed(self.daily, record, True, today=THURSDAY)
    again = services.set_day_completed(self.daily, record, True, today=THURSDAY)
    services.set_day_completed(self.daily, record, False, today=THURSDAY)
    again_off = services.set_day_completed(self.daily, record, False, today=THURSDAY)

    self.assertEqual((again, again_off), (services.NO_COMPLETION_CHANGE,) * 2)
    self.assertEqual(self._xp(self.daily), ((1, 0), (1, 0)))

  # --- semanales: regla B ---
  def test_days_up_to_the_target_give_xp(self):
    self._complete(self.weekly, MONDAY)

    result = self._complete(self.weekly, TUESDAY)

    self.assertEqual(result.xp_habit, 25)  # 2.º día de 3: da XP, todavía sin bonus
    self.assertEqual(result.bonus, services.NO_CHANGE)

  def test_days_beyond_the_target_give_no_xp(self):
    for day in [MONDAY, TUESDAY, WEDNESDAY]:
      self._complete(self.weekly, day)  # meta (3) cumplida, bonus ya cobrado
    xp_before = self._xp(self.weekly)
    record = make_record(self.weekly, THURSDAY, completed=False)

    result = services.set_day_completed(self.weekly, record, True, today=THURSDAY)

    self.assertEqual(result, services.CompletionResult(True, 0, 0, services.NO_CHANGE))
    record.refresh_from_db()
    self.assertEqual((record.completed, record.xp_habit, record.xp_global), (True, 0, 0))
    self.assertEqual(self._xp(self.weekly), xp_before)

  def test_reaching_the_goal_adds_the_period_bonus(self):
    self._complete(self.weekly, MONDAY)
    self._complete(self.weekly, TUESDAY)

    result = self._complete(self.weekly, WEDNESDAY)

    # 25/20 del día + 37/30 del bonus (primera semana de la racha, sin multiplicador)
    self.assertEqual(result.bonus, services.BonusResult("granted", 37, 30))
    self.assertEqual((result.xp_habit, result.xp_global), (62, 50))
    # Total acumulado: 3 días × 25 + 37 = 112 XP de hábito (nivel 2 con 12) y 3 × 20 + 30 = 90 global
    self.assertEqual(self._xp(self.weekly), ((2, 12), (1, 90)))

  def test_uncompleting_the_goal_day_revokes_day_xp_and_bonus(self):
    self._complete(self.weekly, MONDAY)
    self._complete(self.weekly, TUESDAY)
    self._complete(self.weekly, WEDNESDAY)
    record = HabitRecord.objects.get(habit=self.weekly, date__date=WEDNESDAY)

    result = services.set_day_completed(self.weekly, record, False, today=WEDNESDAY)

    self.assertEqual(result.bonus, services.BonusResult("revoked", 37, 30))
    self.assertEqual((result.xp_habit, result.xp_global), (-62, -50))
    self.assertEqual(self._xp(self.weekly), ((1, 50), (1, 40)))  # solo Lunes y Martes
    self.assertFalse(PeriodBonus.objects.exists())

  # --- el agujero que cierra el ledger ---
  def test_editing_the_target_between_mark_and_unmark_cannot_create_xp(self):
    self.weekly.target_per_period = 5
    self.weekly.save()
    for day in [MONDAY, TUESDAY, WEDNESDAY]:
      make_record(self.weekly, day)
    record = make_record(self.weekly, THURSDAY, completed=False)

    services.set_day_completed(self.weekly, record, True, today=THURSDAY)  # 4.º de 5: +25
    self.assertEqual(self._xp(self.weekly), ((1, 25), (1, 20)))

    # El usuario baja la meta a 3: recalculando, el jueves "valdría" 0 y desmarcar restaría 0
    self.weekly.target_per_period = 3
    self.weekly.save()
    services.set_day_completed(self.weekly, record, False, today=THURSDAY)

    # Con el ledger se resta lo que se guardó (25/20). Lo único que queda es el bonus de la
    # meta de 3 días, que Lunes-Miércoles ya cumplen con la meta nueva (37/30). Si se
    # recalculara, se restaría 0 y quedarían 62/50: el jueves habría generado XP de la nada.
    self.assertEqual(self._xp(self.weekly), ((1, 37), (1, 30)))
    self.assertEqual(PeriodBonus.objects.get().xp_habit, 37)