"""
Reglas de negocio de los hábitos por period (día, semana, mes).

Todo lo de este bloque son FUNCIONES PURAS: reciben datos simples (fechas, números)
y devuelven un resultado. No consultan la BD ni leen el reloj: "hoy" siempre llega
como parámetro. Por eso se pueden probar sin base de datos y con cualquier fecha.
"""
import calendar
from datetime import timedelta
from typing import NamedTuple

# XP que da cada registro completado (hoy viven literales en views.py; la Fase 3 los reemplaza)
XP_HABIT_PER_RECORD = 25
XP_GLOBAL_PER_RECORD = 20

# Fórmula del bonus de periodo:
#   bonus = meta × XP por registro × 50% × (100% + 10% × periodos previos cumplidos, máx. 5)
BONUS_PERCENT_OF_TARGET = 50
STREAK_STEP_PERCENT = 10
MAX_STREAK_STEPS = 5

class StreakResult(NamedTuple):
  times: int          # "veces": días completados dentro de la racha
  periods_met: int    # periodos cumplidos dentro de la racha (el actual solo si ya está cumplido)
  at_risk: bool       # hay racha de periodos cumplidos y, si no cumples este periodo, se rompe


def period_bounds(frequency, day):
  """Devuelve (inicio, fin), ambos incluidos, del perodo que contiene `day`."""
  if frequency == "daily":
    return day, day
  if frequency == "weekly":
    # weekday(): lunes = 0 .. doming = 6. Restar esos días lleva siempre al lunes.
    start = day - timedelta(days=day.weekday())
    return start, start + timedelta(days=6)
  if frequency == "monthly":
    last_day = calendar.monthrange(day.year, day.month)[1]  # respeta febrero y bisiestos
    return day.replace(day=1), day.replace(day=last_day)
  raise ValueError(f"Frecuencia desconocida: {frequency}")


def days_done_in_period(completed_days, frequency, day):
  """Cuenta DÍAS DISTINTOS completados en el periodo de `day` (no filas)."""
  start, end = period_bounds(frequency, day)
  return len({d for d in completed_days if start <= d <= end})


def _needed(frequency, target):
  # En un diaro basta un día completado (la meta "por día" ya la resume `completed`).
  # None se interpreta como la meta por defecto (1).
  return 1 if frequency == "daily" else (target or 1)


def is_period_met(completed_days, frequency, target, day):
  """¿Se alcanzó la meta del periodo que contiene `day`?"""
  return days_done_in_period(completed_days, frequency, day) >= _needed(frequency, target)


def streak_by_periods(completed_days, frequency, target, today):
  """
  Racha con tolerancia, evaluada por PERIODOS (la misma regla que la racha diaria):
    - un periodo fallado aislado se perdona; dos seguidos rompen la racha;
    - el periodo en curso no se penaliza
  """
  days = {d for d in completed_days if d <= today}    # los días futuros no existen
  needed = _needed(frequency, target)

  start, _ = period_bounds(frequency, today)
  times = 0
  periods_met = 0
  misses = 0          # periodos fallados consecutivos (el en curso no cuenta)
  pending = 0         # días de periodos perdonados, aún sin confirmar
  current_met = False
  previous_met = None # ¿se cumplió el periodo inmediatamente anterior?
  is_current = True

  while True:
    done = days_done_in_period(days, frequency, start)
    met = done >= needed

    if is_current:
      times += done
      current_met = met
      if met:
        periods_met += 1
    else:
      if previous_met is None:
        previous_met = met
      if met:
        times += pending + done
        periods_met += 1
        pending = 0
        misses = 0
      else:
        misses += 1
        if misses >= 2:
          break   # dos periodos fallados seguidos: la racha termina
        pending += done

    # Retroceder al periodo anterior: el último día del anterior es el día previo al inicio
    start, _ = period_bounds(frequency, start - timedelta(days=1))
    is_current = False

  at_risk = periods_met > 0 and not current_met and previous_met is False
  return StreakResult(times=times, periods_met=periods_met, at_risk=at_risk)

def calculate_period_bonus(frequency, target, previous_periods_met):
  """
  Bonus de XP por cumplir la meta de un period. Devuelve (xp_hábito, xp_global)
  `previous_period_met` = periodos cumplidos de la racha ANTERIORES al actual.
  Solo para semanales y mensuales. Aritmética entera con UN solo redondeo hacia abajo
  """
  if frequency not in ("weekly", "monthly"):
    raise ValueError("Solo los hábitos semanales y mensuales tienen bonus de periodo")

  steps = min(max(previous_periods_met, 0), MAX_STREAK_STEPS)
  # factor sobre 10_000: 50% × (100% + 10% × pasos)  ->  50 × (100 + 10 × pasos) 
  factor = BONUS_PERCENT_OF_TARGET * (100 + STREAK_STEP_PERCENT * steps)
  xp_habit = target * XP_HABIT_PER_RECORD * factor // 10_000
  xp_global = target * XP_GLOBAL_PER_RECORD * factor // 10_000
  return xp_habit, xp_global