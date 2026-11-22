"""
Tests del logout con blacklist del refresh token (POST /api/token/blacklist/).

Qué protege: tras el logout, el refresh token deja de servir para obtener
nuevos access tokens. Qué NO protege (limitación documentada en un test):
el access token ya emitido sigue siendo válido hasta que caduque, porque
el servidor no consulta ninguna tabla para validarlo (JWT sin estado).
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()

LOGIN_URL = "/api/token/"
REFRESH_URL = "/api/token/refresh/"
BLACKLIST_URL = "/api/token/blacklist/"
PROTECTED_URL = "/api/habits/"

PASSWORD = "Sup3r-Segura-123"


class TokenBlacklistTests(TestCase):
  def setUp(self):
    # Los endpoints de tokens son anónimos y tienen throttle de 10/min.
    # El historial del throttle vive en la CACHÉ, que (a diferencia de la BD)
    # NO se revierte entre tests: es estado compartido por toda la suite.
    #  - cache.clear() al empezar: no heredamos peticiones de tests anteriores.
    #  - addCleanup(cache.clear) al terminar (pase o falle): no dejamos
    #    peticiones que provoquen 429 en los tests que corran después.
    # Sin la limpieza final, RegisterEndpointTests fallaba con 429 en CI
    # (suite rápida, todo dentro de la misma ventana de 60 s) y pasaba en
    # local (suite lenta, el historial caducaba): un test inestable.
    cache.clear()
    self.addCleanup(cache.clear)
    self.client = APIClient()
    self.user = User.objects.create_user(username="ana", password=PASSWORD)

  def login(self):
    response = self.client.post(
      LOGIN_URL, {"username": "ana", "password": PASSWORD}, format="json"
    )
    self.assertEqual(response.status_code, 200)
    return response.data["access"], response.data["refresh"]

  def blacklist(self, refresh):
    return self.client.post(BLACKLIST_URL, {"refresh": refresh}, format="json")

  def test_login_records_outstanding_token(self):
    # Esto es lo que daría 500 en producción si falta la migración
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

    _, refresh = self.login()

    jti = RefreshToken(refresh)["jti"]
    self.assertTrue(
      OutstandingToken.objects.filter(jti=jti, user=self.user).exists()
    )

  def test_blacklist_without_access_token_returns_200_and_records_it(self):
    # Sin cabecera Authorization: poseer el refresh es la prueba suficiente
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken

    _, refresh = self.login()
    jti = RefreshToken(refresh)["jti"]

    response = self.blacklist(refresh)

    self.assertEqual(response.status_code, 200)
    self.assertTrue(BlacklistedToken.objects.filter(token__jti=jti).exists())

  def test_blacklisted_refresh_cannot_get_new_access(self):
    _, refresh = self.login()
    self.blacklist(refresh)

    response = self.client.post(REFRESH_URL, {"refresh": refresh}, format="json")

    self.assertEqual(response.status_code, 401)

  def test_blacklisting_same_token_twice_returns_401(self):
    _, refresh = self.login()
    self.blacklist(refresh)

    response = self.blacklist(refresh)

    self.assertEqual(response.status_code, 401)

  def test_other_sessions_keep_working(self):
    # Dos dispositivos: cerrar sesión en uno no cierra el otro
    _, refresh_phone = self.login()
    _, refresh_laptop = self.login()

    self.blacklist(refresh_phone)
    response = self.client.post(
      REFRESH_URL, {"refresh": refresh_laptop}, format="json"
    )

    self.assertEqual(response.status_code, 200)

  def test_missing_refresh_returns_400(self):
    response = self.client.post(BLACKLIST_URL, {}, format="json")

    self.assertEqual(response.status_code, 400)

  def test_garbage_token_returns_401(self):
    response = self.blacklist("esto-no-es-un-jwt")

    self.assertEqual(response.status_code, 401)

  def test_access_token_still_works_after_logout_known_limitation(self):
    # LIMITACIÓN CONOCIDA: el access vive hasta su expiración (30 min).
    # Si algún día este test falla, es que cambió el modelo de sesión:
    # actualiza el CONTEXT.md.
    access, refresh = self.login()
    self.blacklist(refresh)

    self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    response = self.client.get(PROTECTED_URL)

    self.assertEqual(response.status_code, 200)