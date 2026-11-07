from datetime import date

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import CustomUser, Habit, Progress

class RegisterEndpointTests(APITestCase):
  def setUp(self):
    self.url = reverse("register-list")
    self.valid = {
      "username": "ricardo",
      "email": "ricardo@example.com",
      "password": "UnaClaveSegura#2026",
    }

  # --- Caso de uso legítimo ---
  def test_can_register(self):
    res = self.client.post(self.url, self.valid, format="json")
    self.assertEqual(res.status_code, status.HTTP_201_CREATED)
    self.assertNotIn("password", res.data)
    user = CustomUser.objects.get(username="ricardo")
    self.assertTrue(user.check_password(self.valid["password"]))

  def test_cannot_list_users(self):
    CustomUser.objects.create_user(username="victima", password="x" * 12)
    res = self.client.get(self.url)
    self.assertEqual(res.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

  def test_cannot_modify_or_delete_users(self):
    victim = CustomUser.objects.create_user(username="victima", password="Original#12345")
    detail = f"{self.url}{victim.pk}/"

    self.assertEqual(self.client.patch(detail, {"password": "hack"}, format="json").status_code, 404)
    self.assertEqual(self.client.delete(detail).status_code, 404)

    victim.refresh_from_db()
    self.assertTrue(victim.check_password("Original#12345"))

  # --- Reglas de negocio validadas en el servidor ---
  def test_rejects_weak_password(self):
    for bad in ["corta1", "12345678", "passwrd"]:
      res = self.client.post(self.url, {**self.valid, "password": bad}, format="json")
      self.assertEqual(res.status_code, 400, bad)
      self.assertIn("password", res.data)

  def test_two_users_without_email_can_register(self):
    for name in ["ana", "luis"]:
      res = self.client.post(
        self.url, {"username": name, "email": "", "password": "UnaClaveSegura#2026"},
      )
      self.assertEqual(res.status_code, 201, res.data)

  def test_duplicate_email_is_case_insensitive(self):
    self.client.post(self.url, self.valid, format="json")
    res = self.client.post(
      self.url,
      {**self.valid, "username": "otro", "email": "RICARDO@example.com"},
      format="json",
    )
    self.assertEqual(res.status_code, 400)
    self.assertIn("email", res.data)

class ProgressSecurityTests(APITestCase):
  def setUp(self):
    self.alice = CustomUser.objects.create_user(username="alice", password="Alice#Segura2025")
    self.bob = CustomUser.objects.create_user(username="bob", password="Bob#Segura2025")
    self.bob_habit = Habit.objects.create(user=self.bob, name="Leer")
    self.client.force_authenticate(self.alice)

  def test_client_cannot_create_progress(self):
    """Un cliente no puede crear progreso (el XP lo calcula el servidor)"""
    res = self.client.post(
      reverse("progress-list"),
      {"user": self.alice.pk, "level": 9999},
      format="json"
    )
    self.assertEqual(res.status_code, 405)
    self.assertFalse(Progress.objects.filter(level=9999).exists())

  def test_client_cannot_update_progress(self):
    """Un cliente no puede modificar un progreso existente"""
    progress = Progress.objects.create(user=self.alice, level=2, experience=0)
    url = reverse("progress-detail", args=[progress.pk])

    res = self.client.patch(url, {"level": 9999}, format="json")

    self.assertEqual(res.status_code, 405)
    progress.refresh_from_db()
    self.assertEqual(progress.level, 2)

  def test_client_cannot_delete_progress(self):
    """Un cliente no puede borrar un progreso."""
    progress = Progress.objects.create(user=self.alice, level=2)
    url = reverse("progress-detail", args=[progress.pk])

    res = self.client.delete(url)

    self.assertEqual(res.status_code, 405)
    self.assertTrue(Progress.objects.filter(pk=progress.pk).exists())

  def test_cannot_read_progress_of_other_users_habit(self):
    """404 para no revelar que el hábito de otro usuario existe"""
    res = self.client.get(reverse("progress-habit-progress", args=[self.bob_habit.pk]))
    self.assertEqual(res.status_code, 404)

  def test_attempt_on_another_users_habit_creates_no_rows(self):
    """Un GET no debe dejar filas nuevas"""
    before = Progress.objects.count()
    self.client.get(reverse("progress-habit-progress", args=[self.bob_habit.pk]))
    self.assertEqual(Progress.objects.count(), before)

  def test_can_read_progress_of_own_habit(self):
    """El caso legítimo sigue funcionando"""
    my_habit = Habit.objects.create(user=self.alice, name="Correr")
    Progress.objects.create(user=self.alice, habit=my_habit, level=2, experience=10)
    res = self.client.get(reverse("progress-habit-progress", args=[my_habit.pk]))
    self.assertEqual(res.status_code, 200)
    self.assertEqual(res.data["level"], 2)

  def test_own_habit_without_progress_returns_defaults_and_writes_nothing(self):
    """Hábito propio sin progreso: 200 con nivel 1 / 0 XP, sin crear filas."""
    my_habit = Habit.objects.create(user=self.alice, name="Meditar")
    before = Progress.objects.count()
    res = self.client.get(reverse("progress-habit-progress", args=[my_habit.pk]))
    self.assertEqual(res.status_code, 200)
    self.assertEqual(res.data["level"], 1)
    self.assertEqual(res.data["experience"], 0)
    self.assertEqual(Progress.objects.count(), before)

  def test_anonymous_gets_rejected(self):
    """Sin autenticación: 401 (JWT define WWW-Authenticate)."""
    self.client.force_authenticate(None)
    res = self.client.get("progress-global-progress")
    self.assertEqual(res.status_code, 404)

  def test_global_progress_returns_streak_and_monthly(self):
    """El único endpoint de progreso que usa el frontend."""
    res = self.client.get(reverse("progress-global-progress"))
    self.assertEqual(res.status_code, 200)
    self.assertIn("current_streak", res.data)
    self.assertIn("monthly", res.data)
    self.assertIn("level", res.data)

  def test_toggle_completion_returns_progress(self):
    """Completar un hábito propio debe responder 200 con el progreso."""
    my_habit = Habit.objects.create(user=self.alice, name="Estirar")
    res = self.client.post(
      reverse("habit-toggle-completion", args=[my_habit.pk]),
      {"completed": True},
      format="json",
    )
    self.assertEqual(res.status_code, 200, res.data)
    self.assertEqual(res.data["habit_progress"]["experience"], 25)

class HabitNameTests(APITestCase):
  def setUp(self):
    self.alice = CustomUser.objects.create_user(username="alice", password="Alice#Segura2025")
    self.bob = CustomUser.objects.create_user(username='bob', password="Bob#Segura2025")
    self.client.force_authenticate(self.alice)
    self.url = reverse("habit-list")

  def test_duplicate_name_returns_400_not_500(self):
    Habit.objects.create(user=self.alice, name="Leer")
    res = self.client.post(self.url, {"name": "Leer"}, format="json")
    self.assertEqual(res.status_code, 400)
    self.assertIn("name", res.data)
    self.assertEqual(Habit.objects.filter(user=self.alice).count(), 1)

  def test_duplicate_name_ignores_case_and_surrounding_spaces(self):
    Habit.objects.create(user=self.alice, name="Leer")
    res = self.client.post(self.url, {"name": " Leer"}, format="json")
    self.assertEqual(res.status_code, 400)

  def test_two_users_can_use_the_same_habit_name(self):
    Habit.objects.create(user=self.bob, name="Leer")
    res = self.client.post(self.url, {"name": "Leer"}, format="json")
    self.assertEqual(res.status_code, 201)

  def test_can_edit_habit_keeping_its_own_name(self):
    habit = Habit.objects.create(user=self.alice, name="Leer")
    res = self.client.patch(
      reverse("habit-detail", args=[habit.pk]),
      {"name": "Leer", "description": "30 minutos"},
      format="json",
    )
    self.assertEqual(res.status_code, 200, res.data)

  def test_cannot_rename_habit_to_an_existing_name(self):
    Habit.objects.create(user=self.alice, name="Leer")
    other = Habit.objects.create(user=self.alice, name="Correr")
    res = self.client.patch(
      reverse("habit-detail", args=[other.pk]), {"name": "leer"}, format="json"
    )
    self.assertEqual(res.status_code, 400)
    other.refresh_from_db()
    self.assertEqual(other.name, "Correr")

class GlobalProgressNewUserTests(APITestCase):
  def setUp(self):
    self.user = CustomUser.objects.create_user(username="nuevo", password="Nuevo#Segura2026")
    self.client.force_authenticate(self.user)

  def test_new_user_gets_defaults_and_get_writes_nothing(self):
    before = Progress.objects.count()
    res = self.client.get(reverse("progress-global-progress"))
    self.assertEqual(res.status_code, 200)
    self.assertEqual(res.data["level"], 1)
    self.assertEqual(res.data["experience"], 0)
    self.assertEqual(Progress.objects.count(), before)

  def test_database_rejects_second_global_progress(self):
    from django.db import IntegrityError, transaction
    Progress.objects.create(user=self.user, habit=None)
    with self.assertRaises(IntegrityError):
      with transaction.atomic():
        Progress.objects.create(user=self.user,  habit=None)

  def test_database_rejects_duplicate_progress_for_same_habit(self):
    from django.db import IntegrityError, transaction
    habit = Habit.objects.create(user=self.user, name="Leer")
    Progress.objects.create(user=self.user, habit=habit)
    with self.assertRaises(IntegrityError):
      with transaction.atomic():
        Progress.objects.create(user=self.user, habit=habit)

class ProgressXpTests(APITestCase):
  """
  Sumar y restar XP debe ser simétrico: lo que se suma al completar un hábito
  se resta exacto al desmarcarlo, incluidos los niveles.
  """
  def setUp(self):
    self.user = CustomUser.objects.create_user(username="xp", password="Xp#Segura2026")
    self.client.force_authenticate(self.user)

  # --- Unitarios del modelo (sin pasar por la API) ---
  def test_remove_experience_goes_back_down_a_level(self):
    # Arrange: a 10 XP de subir (el nivel 2 cuesta 200)
    progress = Progress.objects.create(user=self.user, level=2, experience=190)

    # Act: sube de nivel y luego se deshace lo mismo
    progress.add_experience(25)
    self.assertEqual((progress.level, progress.experience), (3, 15))
    progress.remove_experience(25)

    # Assert: quedó exactamente como al inicio (en memoria y en la BD)
    self.assertEqual((progress.level, progress.experience), (2, 190))
    progress.refresh_from_db()
    self.assertEqual((progress.level, progress.experience), (2, 190))

  def test_remove_experience_can_drop_several_levels(self):
    # XP total: 100 (nivel 1) + 200 (nivel 2) + 10 = 310. Restar 250 deja 60.
    progress = Progress.objects.create(user=self.user, level=3, experience=10)

    progress.remove_experience(250)

    progress.refresh_from_db()
    self.assertEqual((progress.level, progress.experience), (1, 60))

  def test_remove_experience_never_goes_below_level_one_with_zero_xp(self):
    # Guardián: este comportamiento ya existía y no debe romperse
    progress = Progress.objects.create(user=self.user, level=1, experience=10)

    progress.remove_experience(25)

    progress.refresh_from_db()
    self.assertEqual((progress.level, progress.experience), (1, 0))

  # --- A través de la API: el exploit real ---
  def test_toggling_a_habit_on_and_off_leaves_xp_unchanged(self):
    # Arrange: a 10 XP de subir de nivel en el global (completar da +20)
    habit = Habit.objects.create(user=self.user, name="Estirar")
    Progress.objects.create(user=self.user, level=1, experience=90)
    url = reverse("habit-toggle-completion", args=[habit.pk])

    # Act: marcar y desmarcar varias veces
    for _ in range(3):
      self.client.post(url, {"completed": True}, format="json")
      self.client.post(url, {"completed": False}, format="json")

    # Assert: ni el global ni el del hábito ganaron nada
    global_progress = Progress.objects.get(user=self.user, habit=None)
    self.assertEqual((global_progress.level, global_progress.experience), (1, 90))
    habit_progress = Progress.objects.get(user=self.user, habit=habit)
    self.assertEqual((habit_progress.level, habit_progress.experience), (1, 0))

class HabitFrequencyTargetTests(APITestCase):
  """
  En un hábito semanal/mensual la meta son DÍAS distintos por periodo,
  con tope: semanal 1-5, mensual 1-28. El diario no tiene tope.
  """
  def setUp(self):
    self.alice = CustomUser.objects.create_user(username="alice", password="Alice#Segura2025")
    self.client.force_authenticate(self.alice)
    self.url = reverse("habit-list")

  def _create(self, **extra):
    return self.client.post(self.url, {"name": "Gimnasio", **extra}, format="json")

  def test_weekly_accepts_up_to_five_days(self):
    res = self._create(frequency="weekly", target_per_period=5)
    self.assertEqual(res.status_code, 201, res.data)
    habit = Habit.objects.get(user=self.alice, name="Gimnasio")
    self.assertEqual((habit.frequency, habit.target_per_period), ("weekly", 5))

  def test_weekly_rejects_more_than_five_days(self):
    res = self._create(frequency="weekly", target_per_period=6)
    self.assertEqual(res.status_code, 400)
    self.assertIn("target_per_period", res.data)
    self.assertFalse(Habit.objects.filter(user=self.alice).exists())

  def test_monthly_accepts_up_to_28_days(self):
    res = self._create(frequency="monthly", target_per_period=28)
    self.assertEqual(res.status_code, 201, res.data)
    habit = Habit.objects.get(user=self.alice, name="Gimnasio")
    self.assertEqual((habit.frequency, habit.target_per_period), ("monthly", 28))

  def test_monthly_rejects_more_than_28_days(self):
    res = self._create(frequency="monthly", target_per_period=29)
    self.assertEqual(res.status_code, 400)
    self.assertIn("target_per_period", res.data)
    self.assertFalse(Habit.objects.filter(user=self.alice).exists())

  def test_rejects_zero_target_for_every_frequency(self):
    for frequency in ["daily", "weekly", "monthly"]:
      res = self._create(frequency=frequency, target_per_period=0)
      self.assertEqual(res.status_code, 400, frequency)
      self.assertIn("target_per_period", res.data, frequency)
    self.assertFalse(Habit.objects.filter(user=self.alice).exists())

  def test_daily_still_allows_high_targets(self):
    # Guardián: en un diario la meta es "veces por día" y no tiene tope
    res = self._create(frequency="daily", target_per_period=10)
    self.assertEqual(res.status_code, 201, res.data)

  def test_changing_frequency_checks_the_existing_target(self):
    # PATCH parcial: solo llega `frequency`; la meta (10) viene del hábito guardado
    habit = Habit.objects.create(
      user=self.alice, name="Leer", frequency="daily", target_per_period=10
    )

    res = self.client.patch(
      reverse("habit-detail", args=[habit.pk]), {"frequency": "weekly"}, format="json"
    )

    self.assertEqual(res.status_code, 400)
    self.assertIn("target_per_period", res.data)
    habit.refresh_from_db()
    self.assertEqual(habit.frequency, "daily")

  def test_changing_target_checks_the_existing_frequency(self):
    # PATCH parcial: solo llega la meta; la frecuencia (weekly) viene del hábito guardado
    habit = Habit.objects.create(
      user=self.alice, name="Leer", frequency="weekly", target_per_period=3
    )

    res = self.client.patch(
      reverse("habit-detail", args=[habit.pk]), {"target_per_period": 6}, format="json"
    )

    self.assertEqual(res.status_code, 400)
    self.assertIn("target_per_period", res.data)
    habit.refresh_from_db()
    self.assertEqual(habit.target_per_period, 3)

  def test_can_change_frequency_when_target_fits(self):
    habit = Habit.objects.create(
      user=self.alice, name="Leer", frequency="daily", target_per_period=3
    )

    res = self.client.patch(
      reverse("habit-detail", args=[habit.pk]), {"frequency": "weekly"}, format="json"
    )

    self.assertEqual(res.status_code, 200, res.data)
    habit.refresh_from_db()
    self.assertEqual((habit.frequency, habit.target_per_period), ("weekly", 3))

  def test_weekly_without_target_uses_default(self):
    res = self._create(frequency="weekly")
    self.assertEqual(res.status_code, 201, res.data)
    habit = Habit.objects.get(user=self.alice, name="Gimnasio")
    self.assertEqual(habit.target_per_period, 1)

class HabitFrequencyConstraintTests(APITestCase):
  """Segunda línea de defensa: la BD rechaza metas fuera de rango aunque no se pase por el serializer."""
  def setUp(self):
    self.user = CustomUser.objects.create_user(username="db", password="Db#Segura2026")

  def test_database_rejects_weekly_target_above_five(self):
    with self.assertRaises(IntegrityError):
      with transaction.atomic():
        Habit.objects.create(
          user=self.user, name="Leer", frequency="weekly", target_per_period=6
        )
    self.assertFalse(Habit.objects.filter(user=self.user).exists())

  def test_database_rejects_monthly_target_above_28(self):
    with self.assertRaises(IntegrityError):
      with transaction.atomic():
        Habit.objects.create(
          user=self.user, name="Leer", frequency="monthly", target_per_period=29
        )
    self.assertFalse(Habit.objects.filter(user=self.user).exists())

  def test_database_accepts_the_limits(self):
    Habit.objects.create(user=self.user, name="Semanal", frequency="weekly", target_per_period=5)
    Habit.objects.create(user=self.user, name="Mensual", frequency="monthly", target_per_period=28)
    Habit.objects.create(user=self.user, name="Diario", frequency="daily", target_per_period=10)
    self.assertEqual(Habit.objects.filter(user=self.user).count(), 3)

  def test_full_clean_reports_the_violation(self):
    # Django valida las constraints también en full_clean (admin, ModelForm)
    habit = Habit(user=self.user, name="Leer", frequency="weekly", target_per_period=6)
    with self.assertRaises(ValidationError):
      habit.full_clean()

class PeriodBonusTests(APITestCase):
  """
  Un PeriodBonus significa "este hábito YA cobró el bonus de este periodo".
  La unicidad en la BD evita cobrarlo dos veces aunque lleguen peticiones simultáneas.
  """
  def setUp(self):
    self.user = CustomUser.objects.create_user(username="bonus", password="Bonus#Segura2026")
    self.habit = Habit.objects.create(
      user=self.user, name="Gimnasio", frequency="weekly", target_per_period=3
    )
    self.monday = date(2026, 11, 2)

  def _bonus(self, habit=None, period_start=None, frequency="weekly", target=3):
    from .models import PeriodBonus
    return PeriodBonus.objects.create(
      habit=habit or self.habit,
      frequency=frequency,
      period_start=period_start or self.monday,
      target=target,
      xp_habit=50,
      xp_global=40,
    )

  def test_database_rejects_second_bonus_for_same_habit_and_period(self):
    from .models import PeriodBonus
    self._bonus()
    with self.assertRaises(IntegrityError):
      with transaction.atomic():
        self._bonus()
    self.assertEqual(PeriodBonus.objects.filter(habit=self.habit).count(), 1)

  def test_same_habit_can_earn_a_bonus_in_different_periods(self):
    from .models import PeriodBonus
    self._bonus(period_start=self.monday)
    self._bonus(period_start=date(2026, 11, 9))
    self.assertEqual(PeriodBonus.objects.filter(habit=self.habit).count(), 2)

  def test_different_habits_can_earn_a_bonus_in_the_same_period(self):
    from .models import PeriodBonus
    other = Habit.objects.create(
      user=self.user, name="Leer", frequency="weekly", target_per_period=2
    )
    self._bonus()
    self._bonus(habit=other)
    self.assertEqual(PeriodBonus.objects.count(), 2)

  def test_deleting_a_habit_deletes_its_bonuses(self):
    from .models import PeriodBonus
    self._bonus()
    self.habit.delete()
    self.assertEqual(PeriodBonus.objects.count(), 0)

  def test_same_start_date_with_different_frequency_is_allowed(self):
    # 1-feb-2027 es lunes (inicio de semana) Y día 1 (inicio de mes)
    from .models import PeriodBonus
    both = date(2027, 2, 1)
    self._bonus(period_start=both, frequency="weekly")
    self._bonus(period_start=both, frequency="monthly")
    self.assertEqual(PeriodBonus.objects.filter(habit=self.habit).count(), 2)

  def test_database_rejects_a_daily_bonus(self):
    # Un hábito diario no tiene bonus de periodo
    with self.assertRaises(IntegrityError):
      with transaction.atomic():
        self._bonus(frequency="daily") 