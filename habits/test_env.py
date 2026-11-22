"""
Tests de parse_csv_list: convierte una variable de entorno "a,b,c" en lista.

Motivo: "".split(",") devuelve [''] (una lista con un string vacío), y eso 
acababa en ALLOWED_HOSTS. La función debe devolver [] en ese caso y limpiar
espacios y elementos vacíos.
"""
from django.test import SimpleTestCase

from habit_tracker.env import parse_csv_list


class ParseCsvListTests(SimpleTestCase):
  def test_empty_string_returns_empty_list(self):
    self.assertEqual(parse_csv_list(""), [])

  def test_none_returns_empty_list(self):
    self.assertEqual(parse_csv_list(None), [])

  def test_single_value(self):
    self.assertEqual(parse_csv_list("api.example.com"), ["api.example.com"])

  def test_multiple_values(self):
    self.assertEqual(
      parse_csv_list("a.example.com,b.example.com"),
      ["a.example.com", "b.example.com"],
    )

  def test_strips_spaces_and_drops_empty_items(self):
    self.assertEqual(
      parse_csv_list("a.example.com , b.example.com ,"),
      ["a.example.com", "b.example.com"],
    )

  def test_only_commas_and_spaces_returns_empty_list(self):
    self.assertEqual(parse_csv_list(", ,, "), [])