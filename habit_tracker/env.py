"""
Utilidades para leer configuración desde variables de entorno.

"""


def parse_csv_list(value):
  """
  Convierte "a, b,c," en ["a", "b", "c"].

  - None o "" -> [] (en vez de [""], que es lo que da "".split(","))
  - Quita espacios alrededor de cada elemento.
  - Descarta los elementos vacíos (comas sobrantes o finales).
  """
  if not value:
    return []
  return [item.strip() for item in value.split(",") if item.strip()]