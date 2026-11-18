from datetime import date, datetime, time

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from .models import CustomUser, Habit, HabitRecord, Progress
from .test_endpoints_xp import ApiXpTestCase, at, MONDAY, TUESDAY, WEDNESDAY, THURSDAY

FRIDAY = date(2026, 11, 6)


def completed_record(habit, day):
  return HabitRecord.objects.create(
    habit=habit,
    user=habit.user,
    date=timezone.make_aware(datetime.combine(day, time(0, 0))),
    completed=True,
  )


class TodayApiTests(ApiXpTestCase):
  def today(self, day):
    with at(day):
      return self.client.get(reverse("habit-today"))

  def test_get_today_writes_nothing(self):
    Habit.objects.create(user=self.user, name="Leer")
    Habit.objects.create(user=self.user, name="Gym", frequency="weekly", target_per_period=3)

    res = self.today(THURSDAY)

    self.assertEqual(res.status_code, 200)
    self.assertEqual(len(res.data), 2)
    self.assertFalse(HabitRecord.objects.exists())  # ausencia de registro = no completado
    self.assertFalse(Progress.objects.exists())

  def test_daily_habit_payload(self):
    habit = Habit.objects.create(user=self.user, name="Leer")
    self.toggle(habit, THURSDAY, completed=True)

    res = self.today(THURSDAY)

    self.assertEqual(res.status_code, 200)
    item = res.data[0]
    self.assertEqual(item["id"], habit.id)
    self.assertEqual(item["frequency"], "daily")
    self.assertTrue(item["completed_today"])
    self.assertFalse(item["yesterday_completed"])
    self.assertEqual(item["current_streak"], 1)
    self.assertEqual(item["period"], {"start": "2026-11-05", "end": "2026-11-05"})
    self.assertEqual(item["period_target"], 1)
    self.assertEqual(item["days_done"], 1)
    self.assertTrue(item["period_met"])
    self.assertEqual((item["streak_times"], item["streak_periods"]), (1, 1))
    self.assertFalse(item["at_risk"])
    self.assertIsNone(item["bonus_earned"])
    self.assertEqual(item["week_history"], [False] * 6 + [True])
    self.assertEqual(item["category"], {"id": None, "name": None, "color": None})
    self.assertEqual(item["progress"]["experience"], 25)

  def test_weekly_habit_payload_in_progress_and_with_goal_met(self):
    habit = Habit.objects.create(
      user=self.user, name="Gimnasio", frequency="weekly", target_per_period=3
    )
    self.toggle(habit, MONDAY, completed=True)
    self.toggle(habit, TUESDAY, completed=True)

    item = self.today(TUESDAY).data[0]

    self.assertEqual(item["period"], {"start": "2026-11-02", "end": "2026-11-08"})
    self.assertEqual((item["days_done"], item["period_target"]), (2, 3))
    self.assertFalse(item["period_met"])
    self.assertIsNone(item["bonus_earned"])
    self.assertEqual((item["streak_times"], item["streak_periods"]), (2, 0))
    self.assertFalse(item["at_risk"])

    self.toggle(habit, WEDNESDAY, completed=True)
    item = self.today(WEDNESDAY).data[0]

    self.assertTrue(item["period_met"])
    self.assertEqual(item["bonus_earned"], {"xp_habit": 37, "xp_global": 30})
    self.assertEqual((item["streak_times"], item["streak_periods"]), (3, 1))
    self.assertEqual(item["current_streak"], 3)

  def test_at_risk_comes_from_the_backend(self):
    habit = Habit.objects.create(
      user=self.user, name="Gimnasio", frequency="weekly", target_per_period=3
    )
    for day in [date(2026, 10, 28), date(2026, 10, 20), date(2026, 10, 21), date(2026, 10, 22)]:
      completed_record(habit, day)

    item = self.today(FRIDAY).data[0]

    self.assertTrue(item["at_risk"])
    self.assertEqual((item["streak_times"], item["streak_periods"]), (4, 1))
    self.assertFalse(item["period_met"])
    self.assertEqual(item["days_done"], 0)

  def test_completed_today_only_reflects_todays_record(self):
    habit = Habit.objects.create(
      user=self.user, name="Gimnasio", frequency="weekly", target_per_period=3
    )
    self.toggle(habit, MONDAY, completed=True)

    item = self.today(TUESDAY).data[0]

    self.assertFalse(item["completed_today"])
    self.assertTrue(item["yesterday_completed"])
    self.assertEqual(item["days_done"], 1)

  def test_only_own_habits(self):
    bob = CustomUser.objects.create_user(username="bob", password="Bob#Segura2025")
    mine = Habit.objects.create(user=self.user, name="Leer")
    Habit.objects.create(user=bob, name="Correr")

    res = self.today(THURSDAY)

    self.assertEqual([item["id"] for item in res.data], [mine.id])

  def test_query_count_does_not_grow_with_the_number_of_habits(self):
    Habit.objects.create(user=self.user, name="H0")
    with CaptureQueriesContext(connection) as with_one:
      self.today(THURSDAY)

    for i in range(1, 6):
      habit = Habit.objects.create(
        user=self.user, name=f"H{i}", frequency="weekly", target_per_period=2
      )
      completed_record(habit, THURSDAY)
    with CaptureQueriesContext(connection) as with_six:
      self.today(THURSDAY)

    self.assertEqual(len(with_six), len(with_one))
    self.assertLessEqual(len(with_six), 6)

  def test_requires_authentication(self):
    self.client.force_authenticate(None)
    res = self.client.get(reverse("habit-today"))
    self.assertEqual(res.status_code, 401)

  def test_user_without_habits_gets_an_empty_list(self):
    res = self.today(THURSDAY)
    self.assertEqual(res.status_code, 200)
    self.assertEqual(res.data, [])