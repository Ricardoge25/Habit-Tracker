from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import CustomUser

class RegisterEndpointTests(APITestCase):
  def setUp(self):
    self.url = reverse("register-list")
    self.valid ={
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
    for bad in ["corta1", "12345678", "password"]:
      res = self.client.post(self.url, {**self.valid, "password": bad}, format="json")
      self.assertEqual(res.status_code, 400, bad)
      self.assertIn("password", res.data)

  def test_two_users_without_email_can_register(self):
    for name in ["ana", "luis"]:
      res = self.client.post(
        self.url, {"username": name, "email": "", "password": "UnaClaveSegura#2026"}, format="json"
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
    