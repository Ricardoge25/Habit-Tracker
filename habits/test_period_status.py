from datetime import date

from django.test import SimpleTestCase

from . import services
from .services import PeriodStatus

TODAY = date(2026, 11, 6)  # viernes; semana S0 = 2-8 nov


class WeekHistoryFlagsTests(SimpleTestCase):
  def test_seven_flags_ending_today(self):
    days = {date(2026, 11, 6), date(2026, 11, 4), date(2026, 10, 31)}
    self.assertEqual(
      services.week_history_flags(days, TODAY),
      [True, False, False, False, True, False, True],
    )

  def test_no_days_means_all_false(self):
    self.assertEqual(services.week_history_flags(set(), TODAY), [False] * 7)

  def test_days_outside_the_window_are_ignored(self):
    days = {date(2026, 10, 30), date(2026, 11, 7)}  # uno anterior a la ventana y uno futuro
    self.assertEqual(services.week_history_flags(days, TODAY), [False] * 7)


class PeriodStatusTests(SimpleTestCase):
  def test_daily_done_today(self):
    self.assertEqual(
      services.period_status({TODAY}, "daily", 1, TODAY),
      PeriodStatus(
        period_start=TODAY, period_end=TODAY, days_done=1, period_target=1,
        period_met=True, streak_times=1, streak_periods=1, at_risk=False,
      ),
    )

  def test_daily_pending_today_keeps_yesterdays_streak(self):
    self.assertEqual(
      services.period_status({date(2026, 11, 5)}, "daily", 1, TODAY),
      PeriodStatus(
        period_start=TODAY, period_end=TODAY, days_done=0, period_target=1,
        period_met=False, streak_times=1, streak_periods=1, at_risk=False,
      ),
    )

  def test_weekly_in_progress(self):
    days = {date(2026, 11, 2), date(2026, 11, 4)}
    self.assertEqual(
      services.period_status(days, "weekly", 3, TODAY),
      PeriodStatus(
        period_start=date(2026, 11, 2), period_end=date(2026, 11, 8), days_done=2,
        period_target=3, period_met=False, streak_times=2, streak_periods=0, at_risk=False,
      ),
    )

  def test_weekly_goal_met(self):
    days = {date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 4)}
    self.assertEqual(
      services.period_status(days, "weekly", 3, TODAY),
      PeriodStatus(
        period_start=date(2026, 11, 2), period_end=date(2026, 11, 8), days_done=3,
        period_target=3, period_met=True, streak_times=3, streak_periods=1, at_risk=False,
      ),
    )

  def test_monthly_goal_met(self):
    days = {date(2026, 11, 1), date(2026, 11, 3)}
    self.assertEqual(
      services.period_status(days, "monthly", 2, TODAY),
      PeriodStatus(
        period_start=date(2026, 11, 1), period_end=date(2026, 11, 30), days_done=2,
        period_target=2, period_met=True, streak_times=2, streak_periods=1, at_risk=False,
      ),
    )

  def test_at_risk_when_previous_week_failed_and_this_one_is_open(self):
    days = {
      date(2026, 10, 28),                                          # S-1: 1/3 (fallada)
      date(2026, 10, 20), date(2026, 10, 21), date(2026, 10, 22),  # S-2: 3/3
    }
    self.assertEqual(
      services.period_status(days, "weekly", 3, TODAY),
      PeriodStatus(
        period_start=date(2026, 11, 2), period_end=date(2026, 11, 8), days_done=0,
        period_target=3, period_met=False, streak_times=4, streak_periods=1, at_risk=True,
      ),
    )

  def test_missing_target_is_treated_as_one(self):
    status = services.period_status(set(), "weekly", None, TODAY)
    self.assertEqual(status.period_target, 1)