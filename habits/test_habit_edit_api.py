import warnings
from datetime import datetime, time

from django.urls import reverse
from django.utils import timezone

from .models import Habit, HabitRecord, PeriodBonus, Progress
from .test_endpoints_xp import ApiXpTestCase, at, MONDAY, TUESDAY, WEDNESDAY, THURSDAY


class HabitEditApiTests(ApiXpTestCase):
  def patch(self, habit, day, **body):
    with at(day):
      return self.client.patch(
        reverse("habit-detail", args=[habit.pk]), body, format="json"
      )

  def weekly(self, target):
    return Habit.objects.create(
      user=self.user, name="Gimnasio", frequency="weekly", target_per_period=target
    )

  def test_lowering_the_target_grants_the_bonus_immediately(self):
    habit = self.weekly(5)
    for day in [MONDAY, TUESDAY, WEDNESDAY]:
      self.toggle(habit, day, completed=True)
    self.assertFalse(PeriodBonus.objects.exists())  # 3 días de 5: aún sin bonus

    res = self.patch(habit, THURSDAY, target_per_period=3)

    self.assertEqual(res.status_code, 200, res.data)
    bonus = PeriodBonus.objects.get()
    self.assertEqual((bonus.target, bonus.xp_habit, bonus.xp_global), (3, 37, 30))
    # 3 × 25 + 37 = 112 (nivel 2 con 12) y 3 × 20 + 30 = 90
    self.assertEqual((self.xp(habit), self.xp()), ((2, 12), (1, 90)))

  def test_raising_the_target_keeps_the_bonus_already_earned(self):
    habit = self.weekly(3)
    for day in [MONDAY, TUESDAY, WEDNESDAY]:
      self.toggle(habit, day, completed=True)
    self.assertEqual(PeriodBonus.objects.count(), 1)
    xp_before = (self.xp(habit), self.xp())

    res = self.patch(habit, THURSDAY, target_per_period=5)

    self.assertEqual(res.status_code, 200, res.data)
    self.assertEqual(PeriodBonus.objects.count(), 1)
    self.assertEqual((self.xp(habit), self.xp()), xp_before)

  def test_lowering_the_target_but_still_above_the_days_gives_no_bonus(self):
    habit = self.weekly(5)
    for day in [MONDAY, TUESDAY]:
      self.toggle(habit, day, completed=True)

    res = self.patch(habit, THURSDAY, target_per_period=3)  # 2 días < 3

    self.assertEqual(res.status_code, 200, res.data)
    self.assertFalse(PeriodBonus.objects.exists())

  def test_editing_only_the_name_never_touches_xp(self):
    habit = self.weekly(3)
    for day in [MONDAY, TUESDAY, WEDNESDAY]:  # meta cumplida pero sin pasar por el servicio
      HabitRecord.objects.create(
        habit=habit, user=self.user, completed=True,
        date=timezone.make_aware(datetime.combine(day, time(0, 0))),
      )

    res = self.patch(habit, THURSDAY, name="Gym")

    self.assertEqual(res.status_code, 200, res.data)
    self.assertFalse(PeriodBonus.objects.exists())
    self.assertFalse(Progress.objects.exists())

  def test_changing_frequency_does_not_pay_two_bonuses_for_the_same_days(self):
    habit = self.weekly(3)
    for day in [MONDAY, TUESDAY, WEDNESDAY]:
      self.toggle(habit, day, completed=True)
    xp_before = (self.xp(habit), self.xp())

    res = self.patch(habit, THURSDAY, frequency="monthly")

    self.assertEqual(res.status_code, 200, res.data)
    self.assertEqual(PeriodBonus.objects.count(), 1)  # solo el semanal ya cobrado
    self.assertEqual((self.xp(habit), self.xp()), xp_before)

  def test_habit_list_completed_today_uses_the_local_day(self):
    habit = Habit.objects.create(user=self.user, name="Leer")
    self.toggle(habit, THURSDAY, completed=True)

    with warnings.catch_warnings():
      # El aviso "naive datetime" (comparar el DateTimeField con una fecha) pasa a ser error
      warnings.simplefilter("error", RuntimeWarning)
      with at(THURSDAY):
        res = self.client.get(reverse("habit-list"))

    self.assertEqual(res.status_code, 200)
    self.assertTrue(res.data[0]["completed_today"])