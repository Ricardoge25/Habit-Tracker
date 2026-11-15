from datetime import date, datetime, time
from unittest.mock import patch

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from .models import CustomUser, Habit, HabitRecord, PeriodBonus, Progress

# Referencia de calendario (2026): lunes 2-nov. Semana S0 = 2-8 nov.
MONDAY = date(2026, 11, 2)
TUESDAY = date(2026, 11, 3)
WEDNESDAY = date(2026, 11, 4)
THURSDAY = date(2026, 11, 5)


def at(day):
  """Fija el 'hoy' de la API en `day` (las vistas llaman a timezone.localdate())."""
  return patch("habits.views.timezone.localdate", return_value=day)


class ApiXpTestCase(APITestCase):
  def setUp(self):
    self.user = CustomUser.objects.create_user(username="ana", password="Ana#Segura2026")
    self.client.force_authenticate(self.user)

  def toggle(self, habit, day, **body):
    with at(day):
      return self.client.post(
        reverse("habit-toggle-completion", args=[habit.pk]), body, format="json"
      )

  def update_progress(self, habit, day, direction):
    with at(day):
      return self.client.post(
        reverse("habit-update-progress", args=[habit.pk]), {"direction": direction}, format="json"
      )

  def xp(self, habit=None):
    """(nivel, experiencia) del progreso del hábito, o del global si habit es None."""
    progress = Progress.objects.filter(user=self.user, habit=habit).first()
    return (progress.level, progress.experience) if progress else (1, 0)


class ToggleCompletionApiTests(ApiXpTestCase):
  def test_completing_a_daily_returns_net_xp_and_no_bonus(self):
    habit = Habit.objects.create(user=self.user, name="Leer")

    res = self.toggle(habit, THURSDAY, completed=True)

    self.assertEqual(res.status_code, 200, res.data)
    self.assertEqual(res.data["xp"], {"habit": 25, "global": 20})
    self.assertEqual(res.data["bonus"], {"action": "none", "xp_habit": 0, "xp_global": 0})
    self.assertEqual(res.data["habit_progress"]["experience"], 25)
    self.assertEqual(res.data["global_progress"]["experience"], 20)
    self.assertEqual((res.data["record"]["xp_habit"], res.data["record"]["xp_global"]), (25, 20))

  def test_repeating_the_same_request_does_not_duplicate_xp(self):
    habit = Habit.objects.create(user=self.user, name="Leer")
    self.toggle(habit, THURSDAY, completed=True)

    res = self.toggle(habit, THURSDAY, completed=True)

    self.assertEqual(res.status_code, 200, res.data)
    self.assertEqual(res.data["xp"], {"habit": 0, "global": 0})
    self.assertEqual((self.xp(habit), self.xp()), ((1, 25), (1, 20)))
    self.assertEqual(HabitRecord.objects.filter(habit=habit).count(), 1)

  def test_uncompleting_takes_back_exactly_the_xp(self):
    Progress.objects.create(user=self.user, habit=None, level=1, experience=90)
    habit = Habit.objects.create(user=self.user, name="Leer")
    self.toggle(habit, THURSDAY, completed=True)

    res = self.toggle(habit, THURSDAY, completed=False)

    self.assertEqual(res.data["xp"], {"habit": -25, "global": -20})
    self.assertEqual(self.xp(), (1, 90))  # cruzó de nivel al completar y volvió a bajar

  def test_reaching_the_weekly_goal_returns_the_bonus(self):
    habit = Habit.objects.create(
      user=self.user, name="Gimnasio", frequency="weekly", target_per_period=3
    )
    self.toggle(habit, MONDAY, completed=True)
    self.toggle(habit, TUESDAY, completed=True)

    res = self.toggle(habit, WEDNESDAY, completed=True)

    self.assertEqual(res.data["bonus"], {"action": "granted", "xp_habit": 37, "xp_global": 30})
    self.assertEqual(res.data["xp"], {"habit": 62, "global": 50})
    self.assertEqual(res.data["current_streak"], 3)  # "veces": tres días completados
    self.assertEqual(self.xp(habit), (2, 12))  # 3 × 25 + 37 = 112
    self.assertEqual(self.xp(), (1, 90))       # 3 × 20 + 30 = 90
    self.assertEqual(PeriodBonus.objects.count(), 1)

  def test_days_beyond_the_weekly_target_give_no_xp(self):
    habit = Habit.objects.create(
      user=self.user, name="Gimnasio", frequency="weekly", target_per_period=3
    )
    for day in [MONDAY, TUESDAY, WEDNESDAY]:
      self.toggle(habit, day, completed=True)
    before = (self.xp(habit), self.xp())

    res = self.toggle(habit, THURSDAY, completed=True)

    self.assertEqual(res.data["xp"], {"habit": 0, "global": 0})
    self.assertTrue(res.data["record"]["completed"])
    self.assertEqual((self.xp(habit), self.xp()), before)

  def test_uncompleting_the_goal_day_revokes_the_bonus(self):
    habit = Habit.objects.create(
      user=self.user, name="Gimnasio", frequency="weekly", target_per_period=3
    )
    for day in [MONDAY, TUESDAY, WEDNESDAY]:
      self.toggle(habit, day, completed=True)

    res = self.toggle(habit, WEDNESDAY, completed=False)

    self.assertEqual(res.data["bonus"], {"action": "revoked", "xp_habit": 37, "xp_global": 30})
    self.assertEqual(res.data["xp"], {"habit": -62, "global": -50})
    self.assertEqual((self.xp(habit), self.xp()), ((1, 50), (1, 40)))  # solo Lunes y Martes
    self.assertFalse(PeriodBonus.objects.exists())

  def test_toggle_keeps_progress_consistent_for_multi_goal_dailies(self):
    habit = Habit.objects.create(user=self.user, name="Agua", target_per_period=3)

    on = self.toggle(habit, THURSDAY, completed=True)
    off = self.toggle(habit, THURSDAY, completed=False)

    self.assertEqual(on.data["record"]["progress"], 3)
    self.assertEqual(off.data["record"]["progress"], 0)

  def test_completed_must_be_a_boolean(self):
    habit = Habit.objects.create(user=self.user, name="Leer")

    res = self.toggle(habit, THURSDAY, completed="false")  # la cadena "false" sería True en Python

    self.assertEqual(res.status_code, 400)
    self.assertFalse(HabitRecord.objects.filter(habit=habit).exists())
    self.assertEqual(self.xp(), (1, 0))

  def test_missing_completed_changes_nothing(self):
    habit = Habit.objects.create(user=self.user, name="Leer")

    res = self.toggle(habit, THURSDAY)

    self.assertEqual(res.status_code, 200, res.data)
    self.assertFalse(res.data["record"]["completed"])
    self.assertEqual(res.data["xp"], {"habit": 0, "global": 0})

  def test_a_request_without_note_keeps_the_existing_note(self):
    habit = Habit.objects.create(user=self.user, name="Leer")
    self.toggle(habit, THURSDAY, completed=False, note="Salí a trotar")

    res = self.toggle(habit, THURSDAY, completed=True)

    self.assertEqual(res.data["record"]["note"], "Salí a trotar")

  def test_cannot_toggle_another_users_habit(self):
    bob = CustomUser.objects.create_user(username="bob", password="Bob#Segura2025")
    habit = Habit.objects.create(user=bob, name="Leer")
    records_before = HabitRecord.objects.count()
    progress_before = Progress.objects.count()

    res = self.toggle(habit, THURSDAY, completed=True)

    self.assertEqual(res.status_code, 404)
    self.assertEqual(HabitRecord.objects.count(), records_before)
    self.assertEqual(Progress.objects.count(), progress_before)


class UpdateProgressApiTests(ApiXpTestCase):
  def test_reaching_the_goal_gives_xp_once(self):
    habit = Habit.objects.create(user=self.user, name="Agua", target_per_period=2)

    first = self.update_progress(habit, THURSDAY, "increment")
    second = self.update_progress(habit, THURSDAY, "increment")
    third = self.update_progress(habit, THURSDAY, "increment")  # ya estaba en el tope

    self.assertEqual(first.data["record"]["progress"], 1)
    self.assertFalse(first.data["record"]["completed"])
    self.assertEqual(first.data["xp"], {"habit": 0, "global": 0})
    self.assertTrue(second.data["record"]["completed"])
    self.assertEqual(second.data["xp"], {"habit": 25, "global": 20})
    self.assertEqual(third.data["record"]["progress"], 2)
    self.assertEqual(third.data["xp"], {"habit": 0, "global": 0})
    self.assertEqual((self.xp(habit), self.xp()), ((1, 25), (1, 20)))

  def test_decrementing_from_completed_takes_back_the_xp(self):
    habit = Habit.objects.create(user=self.user, name="Agua", target_per_period=2)
    self.update_progress(habit, THURSDAY, "increment")
    self.update_progress(habit, THURSDAY, "increment")

    res = self.update_progress(habit, THURSDAY, "decrement")

    self.assertEqual(res.data["record"]["progress"], 1)
    self.assertFalse(res.data["record"]["completed"])
    self.assertEqual(res.data["xp"], {"habit": -25, "global": -20})
    self.assertEqual((self.xp(habit), self.xp()), ((1, 0), (1, 0)))

  def test_progress_is_saved_even_when_completion_does_not_change(self):
    habit = Habit.objects.create(user=self.user, name="Agua", target_per_period=3)

    self.update_progress(habit, THURSDAY, "increment")
    self.update_progress(habit, THURSDAY, "increment")

    record = HabitRecord.objects.get(habit=habit)
    self.assertEqual((record.progress, record.completed), (2, False))

  def test_weekly_and_monthly_habits_are_rejected(self):
    for frequency in ["weekly", "monthly"]:
      with self.subTest(frequency=frequency):
        habit = Habit.objects.create(
          user=self.user, name=frequency, frequency=frequency, target_per_period=2
        )

        res = self.update_progress(habit, THURSDAY, "increment")

        self.assertEqual(res.status_code, 400)
    self.assertFalse(HabitRecord.objects.exists())

  def test_invalid_direction_is_rejected(self):
    habit = Habit.objects.create(user=self.user, name="Agua", target_per_period=2)

    res = self.update_progress(habit, THURSDAY, "sideways")

    self.assertEqual(res.status_code, 400)
    self.assertFalse(HabitRecord.objects.filter(habit=habit).exists())

  def test_cannot_update_progress_of_another_users_habit(self):
    bob = CustomUser.objects.create_user(username="bob", password="Bob#Segura2025")
    habit = Habit.objects.create(user=bob, name="Agua", target_per_period=2)

    res = self.update_progress(habit, THURSDAY, "increment")

    self.assertEqual(res.status_code, 404)
    self.assertFalse(HabitRecord.objects.filter(habit=habit).exists())