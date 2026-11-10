from datetime import date, datetime, time, timedelta

from django.test import TestCase
from django.utils import timezone

from . import services
from .models import CustomUser, Habit, HabitRecord, PeriodBonus, Progress

TODAY = date(2026, 11, 6)
MONDAY = date(2026, 11, 2)


def make_record(habit, day, completed=True, at=time(0, 0)):
  """Crea un registro con la fecha/hora LOCAL (America/Bogotá), como hace la API."""
  return HabitRecord.objects.create(
    habit=habit,
    user=habit.user,
    date=timezone.make_aware(datetime.combine(day, at)),
    completed=completed,
  )


class GetCompletedDaysTests(TestCase):
  def setUp(self):
    self.user = CustomUser.objects.create_user(username="ana", password="Ana#Segura2026")
    self.habit = Habit.objects.create(user=self.user, name="Leer")

  def test_returns_only_completed_days(self):
    make_record(self.habit, date(2026, 11, 3), completed=True)
    make_record(self.habit, date(2026, 11, 4), completed=False)
    self.assertEqual(services.get_completed_days(self.habit), {date(2026,11, 3)})

  def test_uses_the_local_day_not_utc(self):
    # 23:59 en Bogotá son las 04:59 UTC del día SIGUIENTE: debe contar como el 4
    make_record(self.habit, date(2026, 11, 4), at=time(23, 59))
    make_record(self.habit, date(2026, 11, 5), at=time(0, 0))
    self.assertEqual(services.get_completed_days(self.habit), {date(2026, 11, 4), date(2026, 11, 5)})

  def test_two_rows_of_the_same_day_count_once(self):
    make_record(self.habit, date(2026, 11, 3), at=time(8, 0))
    make_record(self.habit, date(2026, 11, 3), at=time(20, 0))
    self.assertEqual(services.get_completed_days(self.habit), {date(2026, 11, 3)})

  def test_only_this_habits_records(self):
    other = Habit.objects.create(user=self.user, name="Correr")
    make_record(other, date(2026, 11, 3))
    self.assertEqual(services.get_completed_days(self.habit), set())
  

class DailyStreakCharacterizationTests(TestCase):
  """
  Test de caracterización: la lógica nueva debe dar el MISMO número que la racha diaria
  actual (Habit.current_streak) con registros reales. Protege contra regresiones y es lo
  que permitirá unificar las dos rachas más adelante.
  """
  def setUp(self):
    self.user = CustomUser.objects.create_user(username="ana", password="Ana#Segura2026")
    self.habit = Habit.objects.create(user=self.user, name="Leer")

  def test_new_streak_matches_current_streak_for_many_patterns(self):
    # Cada patrón son días hacia atrás desde hoy (0 = hoy, 1 = ayer...)
    patterns = [
      [], [0], [1], [0, 1, 2], [1, 2, 3], [0, 2, 3], [0, 3, 4], [3], [1, 3],
      [2, 3, 4, 6, 7], [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 3, 5, 7, 9], [0, 2, 4, 6],
      [4, 5, 6], [2, 3],
    ]
    for offsets in patterns:
      with self.subTest(offsets=offsets):
        HabitRecord.objects.filter(habit=self.habit).delete()
        for offset in offsets:
          make_record(self.habit, TODAY - timedelta(days=offset))

        old = self.habit.current_streak(upto=TODAY)
        new = services.streak_by_periods(
          services.get_completed_days(self.habit), "daily", 1, TODAY
        )

        self.assertEqual(new.times, old)


class SyncPeriodBonus(TestCase):
  def setUp(self):
    self.user = CustomUser.objects.create_user(username="ana", password="Ana#Segura2026")
    self.habit = Habit.objects.create(
      user=self.user, name="Gimnasio", frequency="weekly", target_per_period=3
    )

  # --- helpers ---
  def _week(self, monday, days_done, habit=None):
    for i in range(days_done):
      make_record(habit or self.habit, monday + timedelta(days=1))

  def _xp(self):
    habit_progress = Progress.objects.filter(user=self.user, habit=self.habit).first()
    global_progress = Progress.objects.filter(user=self.user, habit=None).first()
    return (
      (habit_progress.level, habit_progress.experience) if habit_progress else (1, 0), 
      (global_progress.level, global_progress.experience) if global_progress else (1, 0),
    )

  # --- otorgar ---
  def test_no_bonus_before_reaching_the_goal(self):
    self._week(MONDAY, 2)

    result = services.sync_period_bonus(self.habit, today=TODAY)

    self.assertEqual(result, services.NO_CHANGE)
    self.assertFalse(PeriodBonus.objects.exists())
    self.assertEqual(self._xp(), ((1, 0), (1, 0)))

  def test_reaching_the_goal_grants_the_bonus(self):
    self._week(MONDAY, 3)

    result = services.sync_period_bonus(self.habit, today=TODAY)

    self.assertEqual(result, services.BonusResult("granted", 37, 30))
    bonus = PeriodBonus.objects.get()
    self.assertEqual(
      (bonus.habit_id, bonus.frequency, bonus.period_start, bonus.target, bonus.xp_habit, bonus.xp_global),
      (self.habit.id, "weekly", MONDAY, 3, 37, 30),
    )
    self.assertEqual(self._xp(), ((1, 37), (1, 30)))

  def test_streak_of_previous_weeks_raises_the_bonus(self):
    # 4 semanas previas cumplidas (3/3 cada una) + la actual: multiplicador de 4 pasos
    for weeks_back in range(1, 5):
      self._week(MONDAY - timedelta(weeks=weeks_back), 3)
    self._week(MONDAY, 3)

    result = services.sync_period_bonus(self.habit, today=TODAY)
    
    self.assertEqual(result, services.BonusResult("granted", 52, 42))

  def test_is_idempotent(self):
    self._week(MONDAY, 3)

    first = services.sync_period_bonus(self.habit, today=TODAY)
    second = services.sync_period_bonus(self.habit, today=TODAY)
    third = services.sync_period_bonus(self.habit, today=TODAY)

    self.assertEqual(first.action, "granted")
    self.assertEqual((second, third), (services.NO_CHANGE, services.NO_CHANGE))
    self.assertEqual(PeriodBonus.objects.count(), 1)
    self.assertEqual(self._xp(), ((1, 37), (1, 30)))

  # --- revocar ---
  def test_dropping_below_the_goal_revokes_the_bonus(self):
    self._week(MONDAY, 3)
    services.sync_period_bonus(self.habit, today=TODAY)

    HabitRecord.objects.filter(habit=self.habit).order_by("date").last().delete()
    result = services.sync_period_bonus(self.habit, today=TODAY)

    self.assertEqual(result, services.BonusResult("revoked", 37, 30))
    self.assertFalse(PeriodBonus.objects.exists())
    self.assertEqual(self._xp(), ((1, 0), (1, 0)))

  def test_revoke_takes_back_exactly_what_was_stored(self):
    # El bonus se guardó con 50/40 (otra fórmula, otra época): se resta eso, no 37/30
    PeriodBonus.objects.create(
      habit=self.habit, frequency="weekly", period_start=MONDAY, target=3,
      xp_habits=50, xp_global=40,
    )
    Progress.objects.create(user=self.user, habit=self.habit, level=1, experience=50)
    Progress.objects.create(user=self.user, habit=None, level=1, experience=40)
    self._week(MONDAY, 2)

    result = services.sync_period_bonus(self.habit, today=TODAY)

    self.assertEqual(result, services.BonusResult("revoked", 50, 40))
    self.assertEqual(self._xp(), ((1, 0), (1,0)))

  def test_grant_then_revoke_leaves_levels_untouched(self):
    # A 10 XP de subir: el bonus (37/30) cruza de nivel; revocarlo debe bajar de nivel
    Progress.objects.create(user=self.user, habit=self.habit, level=1, experience=90)
    Progress.objects.create(user=self.user, habit=None, level=1, experience=90)
    self._week(MONDAY, 3)

    services.sync_period_bonus(self.habit, today=TODAY)
    self.assertEqual(self._xp(), ((2, 27), (2, 20)))

    HabitRecord.objects.filter(habit=self.habit).order_by("date").last().delete()
    services.sync_period_bonus(self.habit, today=TODAY)
    self.assertEqual(self._xp(), ((1, 90), (1, 90)))

  # --- reglas de borde ---
  def test_closed_periods_are_never_touched(self):
    last_monday = MONDAY - timedelta(weeks=1)
    PeriodBonus.objects.create(
      habit=self.habit, frequency="weekly", period_start=last_monday, target=3,
      xp_habit=37, xp_global=30
    )
    self._week(last_monday, 1)  # la semana pasada quedó por debajo de la meta (editada a posteriori)

    result = services.sync_period_bonus(self.habit, today=TODAY)

    self.assertEqual(result, services.NO_CHANGE)
    self.assertFalse(PeriodBonus.objects.filter(period_start=last_monday).exists())

  def test_daily_habits_have_no_bonus(self):
    daily = Habit.objects.create(user=self.user, name="Meditar", frequency="daily")
    make_record(daily, TODAY)

    result = services.sync_period_bonus(daily, today=TODAY)

    self.assertEqual(result, services.NO_CHANGE)
    self.assertFalse(PeriodBonus.objects.exists())

  def test_changing_frequency_does_not_double_dip_in_the_same_period(self):
    self._week(MONDAY, 3)
    services.sync_period_bonus(self.habit, today=TODAY)
    self.habit.frequency = "monthly"
    self.habit.save()

    result = services.sync_period_bonus(self.habit, today=TODAY)

    self.assertEqual(result, services.NO_CHANGE)
    self.assertEqual(PeriodBonus.objects.count(), 1)
    
  def test_after_changing_frequency_the_next_period_can_earn_again(self):
    self._week(MONDAY, 3)
    services.sync_period_bonus(self.habit, today=TODAY)
    self.habit.frequency = "monthly"
    self.habit.save() 
    december_day = date(2026, 12, 8)
    for day in [date(2026, 12, 1), date(2026, 12, 2), date(2026, 12, 3)]:
      make_record(self.habit, day)

    result = services.sync_period_bonus(self.habit, today=december_day)

    self.assertEqual(result.action, "granted")
    self.assertEqual(PeriodBonus.objects.filter(frequency="monthly").count(), 1)