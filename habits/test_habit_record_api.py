from datetime import datetime, time

from django.utils import timezone

from .models import Habit, HabitRecord, PeriodBonus
from .test_endpoints_xp import ApiXpTestCase, MONDAY, WEDNESDAY


class HabitRecordApiRetiredTests(ApiXpTestCase):
  """
  El CRUD de registros se retiró: un registro solo cambia mediante toggle-completion y 
  update-progress, que son los que calculan el XP y operan siempre sobre HOY.
  """
  def setUp(self):
    super().setUp()
    self.habit = Habit.objects.create(
      user=self.user, name="Gimnasio", frequency="weekly", target_per_period=3
    )
    self.record = HabitRecord.objects.create(
      habit=self.habit, user=self.user, completed=False,
      date=timezone.make_aware(datetime.combine(MONDAY, time(0, 0))),
    )

  def test_list_is_gone(self):
    self.assertEqual(self.client.get("/api/habit-record/").status_code, 404)

  def test_create_is_gone(self):
    res = self.client.post(
      "/api/habit-record/",
      {"habit": self.habit.pk, "date": "2026-11-03T00:00:00-05:00", "completed": True},
      format="json",
    )
    self.assertEqual(res.status_code, 404)
    self.assertEqual(HabitRecord.objects.count(), 1)

  def test_update_is_gone(self):
    res = self.client.patch(
      f"/api/habit-record/{self.record.pk}/", {"completed": True}, format="json"
    )
    self.assertEqual(res.status_code, 404)
    self.record.refresh_from_db()
    self.assertFalse(self.record.completed)

  def test_delete_is_gone(self):
    res = self.client.delete(f"/api/habit-record/{self.record.pk}/")
    self.assertEqual(res.status_code, 404)
    self.assertTrue(HabitRecord.objects.filter(pk=self.record.pk).exists())

  def test_cannot_fabricate_records_to_earn_the_bonus(self):
    # El ataque: fabricar los días de Lunes y Martes con dos POST y marcar solo el Miércoles
    other = Habit.objects.create(
      user=self.user, name="Otro", frequency="weekly", target_per_period=3
    )
    for day in ["2026-11-02", "2026-11-03"]:
      self.client.post(
        "/api/habit-record/",
        {"habit": other.pk, "date": f"{day}T00:00:00-05:00", "completed": True},
        format="json",
      )

    res = self.toggle(other, WEDNESDAY, completed=True)

    self.assertEqual(res.status_code, 200, res.data)
    self.assertEqual(res.data["bonus"]["action"], "none")
    self.assertFalse(PeriodBonus.objects.exists())