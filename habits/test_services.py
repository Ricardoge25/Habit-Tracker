from datetime import date

from django.test import SimpleTestCase

from . import services
from .models import MAX_MONTHLY_TARGET, MAX_WEEKLY_TARGET
from .services import StreakResult

TODAY = date(2026, 11, 6)


class PeriodBoundsTests(SimpleTestCase):
  """Funciones puras: SimpleTestCase no toca la BD, así que corre en milisegundos."""

  def test_table_of_period(self):
    cases = [
      # (frecuencia, día (inicio, fin))
      ("daily", date(2026, 11, 4), (date(2026, 11, 4), date(2026, 11, 4))),
      # semana: miércoles, lunes y domingo pertenecen a la MISMA semana
      ("weekly", date(2026, 11, 4), (date(2026, 11, 2), date(2026, 11, 8))),
      ("weekly", date(2026, 11, 2), (date(2026, 11, 2), date(2026, 11, 8))),
      ("weekly", date(2026, 11, 8), (date(2026, 11, 2), date(2026, 11, 8))),
      # domingo -> lunes: el lunes abre una semana nueva
      ("weekly", date(2026, 11, 9), (date(2026, 11, 9), date(2026, 11, 15))),
      # la semana cruza de mes y de año
      ("weekly", date(2026, 12, 2), (date(2026, 11, 30), date(2026, 12, 6))),
      ("weekly", date(2027, 1, 1), (date(2026, 12, 28), date(2027, 1, 3))),
      # mes natural: 30, 31, 28 días y bisiesto
      ("monthly", date(2026, 11, 15), (date(2026, 11, 1), date(2026, 11, 30))),
      ("monthly", date(2026, 12, 31), (date(2026, 12, 1), date(2026, 12, 31))),
      ("monthly", date(2027, 2, 10), (date(2027, 2, 1), date(2027, 2, 28))),
      ("monthly", date(2028, 2, 10), (date(2028, 2, 1), date(2028, 2, 29))),
      ("monthly", date(2028, 2, 29), (date(2028, 2, 1), date(2028, 2, 29))),
    ]
    for frequency, day, expected in cases:
      with self.subTest(frequency=frequency, day=day):
        self.assertEqual(services.period_bounds(frequency, day), expected)

  def test_unknown_frequency_raises(self):
    with self.assertRaises(ValueError):
      services.period_bounds("yearly", TODAY)

class DaysDoneTests(SimpleTestCase):
  def test_counts_distinct_days_not_rows(self):
    # Tres filas del mismo días (algo que la API permite hoy) valen UN día
    rows = [date(2026, 11, 3), date(2026, 11, 3), date(2026, 11, 3)]
    self.assertEqual(services.days_done_in_period(rows, "weekly", TODAY), 1)

  def test_period_limits_are_inclusive_and_neighbours_are_excluded(self):
    days = {
      date(2026, 11, 1),    # domingo de la semana anterior: fuera
      date(2026, 11, 2),    # lunes: dentro
      date(2026, 11, 8),    # domingo: dentro
      date(2026, 11, 9),    # lunes siguiente: fuera
    }
    self.assertEqual(services.days_done_in_period(days, "weekly", TODAY), 2)

  def test_is_period_met_weekly_and_monthly(self):
    two = {date(2026, 11, 2), date(2026, 11, 3)}
    three = two | {date(2026, 11, 4)}
    self.assertFalse(services.is_period_met(two, "weekly", 3, TODAY))
    self.assertTrue(services.is_period_met(three, "weekly", 3, TODAY))
    self.assertTrue(services.is_period_met(two, "monthly", 2, TODAY))

  def test_is_period_met_daily_needs_one_day_whatever_the_target(self):
    self.assertTrue(services.is_period_met({TODAY}, "daily", 5, TODAY))
    self.assertFalse(services.is_period_met(set(), "daily", 5, TODAY))

  def test_missing_target_is_treated_as_one(self):
    self.assertTrue(services.is_period_met({TODAY}, "weekly", None, TODAY))

class DailyStreakTests(SimpleTestCase):
  """La racha diaria por periodos debe comportarse como la actual (Habit.current_streak)."""

  def streak(self, days):
    return services.streak_by_periods(days, "daily", 1, TODAY)

  def test_no_records_no_streak(self):
    self.assertEqual(self.streak(set()), StreakResult(0, 0, False))

  def test_today_completed_counts(self):
    self.assertEqual(self.streak({TODAY}), StreakResult(1, 1, False))

  def test_today_pending_is_nt_penalised(self):
    # Solo ayer: hoy aún no termina, la racha sigue viva
    self.assertEqual(self.streak({date(2026, 11, 5)}), StreakResult(1, 1, False))

  def test_one_isolated_miss_is_forgiven(self):
    days = {date(2026, 11, 6), date(2026, 11, 4), date(2026, 11, 3)}  # falta el 5
    self.assertEqual(self.streak(days), StreakResult(3, 3, False))

  def test_two_consecutive_misses_break_the_streak(self):
    days = {date(2026, 11, 6), date(2026, 11, 3), date(2026, 11, 2)}   # faltan el 4 y el 5
    self.assertEqual(self.streak(days), StreakResult(1, 1, False))

  def test_today_pending_and_two_before_means_zero(self):
    self.assertEqual(self.streak({date(2026, 11, 3)}), StreakResult(0, 0, False))

  def test_at_risk_when_today_and_yesterday_are_missing(self):
    # Hoy pendiente, ayer fallado, antepenúltimo día cumplido: fallar hoy rompe la racha
    self.assertEqual(self.streak({date(2026, 11, 4)}), StreakResult(1, 1, True))

  def test_future_days_are_ignored(self):
    self.assertEqual(self.streak({TODAY, date(2026, 11, 7)}), StreakResult(1, 1, False))

class PeriodStreakTests(SimpleTestCase):
  def test_weekly_streak_counts_times_and_forgives_one_partial_week(self):
    days = {
      date(2026, 11, 2), date(2026, 11, 4),                       # S0 (en curso): 2/3
      date(2026, 10, 26), date(2026, 10, 28), date(2026, 10, 30),  # S-1: 3/3
      date(2026, 10, 20),                                          # S-2: 1/3 (perdonada)
      date(2026, 10, 12), date(2026, 10, 14), date(2026, 10, 16),  # S-3: 3/3
    }
    result = services.streak_by_periods(days, "weekly", 3, TODAY)
    self.assertEqual(result, StreakResult(times=9, periods_met=2, at_risk=False))

  def test_two_consecutive_missed_weeks_break_the_streak(self):
    days = {
      date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 4),     # S0: 3/3
      date(2026, 10, 20),                                          # S-2: 1/3 (fallada)
      date(2026, 10, 12), date(2026, 10, 14), date(2026, 10, 16),  # S-3: 3/3 (ya no cuenta)
    }
    result = services.streak_by_periods(days, "weekly", 3, TODAY)
    self.assertEqual(result, StreakResult(times=3, periods_met=1, at_risk=False))

  def test_current_week_empty_is_not_penalised(self):
    days = {date(2026, 10, 26), date(2026, 10, 27), date(2026, 10, 28)}   # S-1: 3/3
    result = services.streak_by_periods(days, "weekly", 3, TODAY)
    self.assertEqual(result, StreakResult(times=3, periods_met=1, at_risk=False))

  def test_weekly_at_risk_when_previous_week_failed_and_this_one_is_open(self):
    days = {
      date(2026, 10, 28),                                           # S-1: 1/3 (fallada)
      date(2026, 10, 20), date(2026, 10, 21), date(2026, 10, 22)    # S-2: 3/3
    }
    result = services.streak_by_periods(days, "weekly", 3, TODAY)
    self.assertEqual(result, StreakResult(times=4, periods_met=1, at_risk=True))

  def test_new_habit_first_week_is_not_at_risk(self):
    # Una semana a medias sin ninguna semana cumplida antes: no hay racha que perder
    result = services.streak_by_periods({date(2026, 11, 3)}, "weekly", 3, TODAY)
    self.assertEqual(result, StreakResult(times=1, periods_met=0, at_risk=False))

  def test_monthly_streak_forgives_one_partial_month(self):
    days = {
      date(2026, 11, 1), date(2026, 11, 3),   # nov: 2/2
      date(2026, 10, 15),                     # oct: 1/2 (perdonado)
      date(2026, 9, 5), date(2026, 9, 20),    # sep: 2/2
    }
    result = services.streak_by_periods(days, "monthly", 2, TODAY)
    self.assertEqual(result, StreakResult(times=5, periods_met=2, at_risk=False))

  def test_streak_crosses_the_year_boundary(self):
    today = date(2027, 1, 5) # martes
    days = {date(2027, 1, 4), date(2026, 12, 29), date(2026, 12, 22)} # una por semana
    result = services.streak_by_periods(days, "weekly", 1, today)
    self.assertEqual(result, StreakResult(times=3, periods_met=3, at_risk=False))

class PeriodBonusFormulaTests(SimpleTestCase):
  def test_table_of_bonuses(self):
    cases = [
      # (frecuencia, meta, periodos previos, (XP hábito, XP global))
      ("weekly", 1, 0, (12, 10)),
      ("weekly", 3, 0, (37, 30)),
      ("weekly", 3, 4, (52, 42)),    # 52,5 se redondea hacia abajo UNA sola vez
      ("weekly", 3, 5, (56, 45)),
      ("weekly", 3, 99, (56, 45)),   # el multiplicador tiene tope: 5 periodos
      ("monthly", 12, 0, (150, 120)),
      ("monthly", 12, 5, (225, 180)),
    ]
    for frequency, target, previous, expected in cases:
      with self.subTest(frequency=frequency, target=target, previous=previous):
        self.assertEqual(services.calculate_period_bonus(frequency, target, previous), expected)

  def test_ceiling_with_the_highest_allowed_targets(self):
    # El techo del sistema sale de los límites de meta (5 y 28) y del tope del multiplicador.
    # Si alguien sube un límite, este test falla y obliga a pensar en el impacto en el XP.
    self.assertEqual(services.calculate_period_bonus("weekly", MAX_WEEKLY_TARGET, 99), (93, 75))
    self.assertEqual(services.calculate_period_bonus("monthly", MAX_MONTHLY_TARGET, 99), (525, 420))

  def test_bonus_never_exceeds_the_ceiling_for_any_allowed_input(self):
    for target in range(1, MAX_WEEKLY_TARGET + 1):
      for previous in range(0, 12):
        habit_xp, global_xp = services.calculate_period_bonus("weekly", target, previous)
        self.assertLessEqual(habit_xp, 93)
        self.assertLessEqual(global_xp, 75)
    for target in range(1, MAX_MONTHLY_TARGET + 1):
      for previous in range(0, 12):
        habit_xp, global_xp = services.calculate_period_bonus("monthly", target, previous)
        self.assertLessEqual(habit_xp, 525)
        self.assertLessEqual(global_xp, 420)

  def test_negative_previous_periods_are_treated_as_zero(self):
    self.assertEqual(services.calculate_period_bonus("weekly", 3, -2), (37, 30))

  def test_daily_habits_have_no_period_bonus(self):
    with self.assertRaises(ValueError):
      services.calculate_period_bonus("daily", 1, 0)
