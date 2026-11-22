"""
Tests de CORS.

Recordatorio clave: CORS NO bloquea peticiones en el servidor. Un origen no
permitido recibe la misma respuesta (aquí, 401); lo único que cambia es que
el servidor NO envía Access-Control-Allow-Origin, y es el NAVEGADOR el que
impide al JavaScript de ese origen leer la respuesta. Por eso los tests
comprueban la cabecera, no el código de estado.
"""
from django.conf import settings
from django.test import TestCase, override_settings

NETLIFY = "https://my-habitflow-app.netlify.app"
LOCALHOST = "http://localhost:5173"
EVIL = "https://evil.example.com"

ALLOWED = [NETLIFY, LOCALHOST]

# Endpoint protegido: sin token responde 401 antes de llegar al throttling
PROTECTED_URL = "/api/habits/"
# Endpoint público que el navegador consulta con preflight (POST con JSON)
TOKEN_URL = "/api/token/"


class CorsConfigTests(TestCase):
  def test_allow_all_origins_is_disabled(self):
    self.assertFalse(getattr(settings, "CORS_ALLOW_ALL_ORIGINS", False))


@override_settings(CORS_ALLOWED_ORIGINS=ALLOWED)
class CorsBehaviourTests(TestCase):
  def test_allowed_origin_receives_its_own_origin_header(self):
    for origin in ALLOWED:
      with self.subTest(origin=origin):
        response = self.client.get(PROTECTED_URL, headers={"origin": origin})

        self.assertEqual(
          response.headers.get("Access-Control-Allow-Origin"),
          origin,
          msg=f"status={response.status_code} headers={dict(response.headers)}",
        )

  def test_unknown_origin_gets_no_cors_header(self):
    response = self.client.get(PROTECTED_URL, headers={"origin": EVIL})

    # El servidor responde igual: CORS no es un firewall
    self.assertEqual(response.status_code, 401)
    self.assertNotIn("Access-Control-Allow-Origin", response.headers)

  def test_preflight_from_allowed_origin_is_authorized(self):
    response = self.client.options(
      TOKEN_URL,
      headers={
        "origin": NETLIFY,
        "access-control-request-method": "POST",
        "access-control-request-headers": "authorization, content-type",
      },
    )

    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), NETLIFY)
    self.assertIn(
      "authorization",
      response.headers.get("Access-Control-Allow-Headers", "").lower(),
    )

  def test_preflight_from_unknown_origin_is_not_authorized(self):
    response = self.client.options(
      TOKEN_URL,
      headers={
        "origin": EVIL,
        "access-control-request-method": "POST",
      },
    )

    self.assertNotIn("Access-Control-Allow-Origin", response.headers)