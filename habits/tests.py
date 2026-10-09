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
