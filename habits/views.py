from rest_framework import viewsets, permissions, status, generics, mixins
from rest_framework.exceptions import ValidationError
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import datetime, time, timedelta
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.contrib.auth import get_user_model
from . import services
from .models import Habit, HabitRecord, CustomUser, Category, Progress, PeriodBonus
from .serializers import (
  HabitSerializer,
  HabitRecordSerializer,
  RegisterSerializer,
  CategorySerializer,
  ProgressSerializer,
)

#--------------------------------------------------------
# 📁 Categoría
#--------------------------------------------------------
class CategoryViewSet(viewsets.ModelViewSet):
  serializer_class = CategorySerializer
  permission_classes = [permissions.IsAuthenticated]

  def get_queryset(self):
    return Category.objects.filter(user=self.request.user)

  def perform_create(self, serializer):
    serializer.save(user=self.request.user)

#--------------------------------------------------------
# 💡 Hábitos
#--------------------------------------------------------
class HabitViewSet(viewsets.ModelViewSet):
  serializer_class = HabitSerializer
  permission_classes = [permissions.IsAuthenticated]

  def get_queryset(self):
    return Habit.objects.filter(user=self.request.user)

  def _save_or_400(self, serializer, **kwargs):
    """
    Red de seguridad: validate_name ya rechaza duplicados, pero si dos peticiones
    simultáneas pasan esa validación a la vez, la restricción única de la BD gana.
    Lo convertimos en 400 (error del cliente) en lugar de un 500.
    atomic() evita dejar rota la transacción tras el IntegrityError.
    """
    try:
      with transaction.atomic():
        serializer.save(**kwargs)
    except IntegrityError:
      raise ValidationError({"name": ["Ya tienes un hábito con ese nombre."]})

  def perform_create(self, serializer):
    self._save_or_400(serializer, user=self.request.user)

  def perform_update(self, serializer):
    with transaction.atomic():
      self._save_or_400(serializer)
      # El bonus de periodo se deriva de la meta y la frecuencia: si cambian, se re-sincroniza
      # en el acto (si no, el XP dependería de qué endpoint se llame después).
      if {"frequency", "target_per_period"} & set(serializer.validated_data):
        services.sync_period_bonus(serializer.instance)

  def update(self, request, *args, **kwargs):
    """Evita que al editar se reinicien campos no enviados."""
    kwargs['partial'] = True 
    return super().update(request, *args, **kwargs)

  # ---------- Apoyo para las acciones de completado ----------
  def _completion_response(self, habit, record, result, today):
    """
    Respuesta común de toggle-completion y update-progress.
    Se RELEEN los Progress de la BD: el bonus los modifica con otras instancias,
    así que los que tenía la vista quedaron desactualizados.
    """
    user = self.request.user
    global_progress = (
      Progress.objects.filter(user=user, habit=None).first() or Progress(user=user, habit=None)
    )
    habit_progress = (
      Progress.objects.filter(user=user, habit=habit).first() or Progress(user=user, habit=habit)
    )
    return Response({
      "record": HabitRecordSerializer(record).data,
      "habit_progress": ProgressSerializer(habit_progress).data,
      "global_progress": ProgressSerializer(global_progress).data,
      "current_streak": services.get_streak(habit, today).times,
      "xp": {"habit": result.xp_habit, "global": result.xp_global},
      "bonus": {
        "action": result.bonus.action,
        "xp_habit": result.bonus.xp_habit,
        "xp_global": result.bonus.xp_global,
      },
    }, status=status.HTTP_200_OK)

  @action(detail=True, methods=["post"], url_path="toggle-completion")
  def toggle_completion(self, request, pk=None):
    habit = self.get_object()
    today = timezone.localdate()

    # No confiar en el tipo que manda el cliente: bool("false") es True en Python
    completed = request.data.get("completed", None)
    if completed is not None and not isinstance(completed, bool):
      return Response(
        {"detail": "completed debe ser true o false."},
        status=status.HTTP_400_BAD_REQUEST,
      )
    note = request.data.get("note", None)  # solo se modifica si el cliente la envía

    with transaction.atomic():
      record = services.get_or_create_today_record(habit, request.user, today)
      if note is not None:
        record.note = note

      wanted = record.completed if completed is None else completed
      if wanted != record.completed:
        # El contador de repeticiones y el estado "completado" no pueden contradecirse
        if wanted:
          record.progress = (habit.target_per_period or 1) if habit.frequency == "daily" else 1
        else:
          record.progress = 0

      # Toda la lógica de XP vive en el servicio: la vista no decide nada
      result = services.set_day_completed(habit, record, wanted, today)
      if not result.changed:
        record.save()  # el estado no cambió, pero la nota sí pudo cambiar

    return self._completion_response(habit, record, result, today)

  @action(detail=True, methods=["post"], url_path="update-progress")
  def update_progress(self, request, pk=None):
    habit = self.get_object()
    today = timezone.localdate()

    # Este endpoint cuenta repeticiones DENTRO de un día. En semanales y mensuales la
    # meta son días, y se completan día a día con toggle-completion.
    if habit.frequency != "daily":
      return Response(
        {"detail": "Los hábitos semanales y mensuales se completan con toggle-completion."},
        status=status.HTTP_400_BAD_REQUEST,
      )

    direction = request.data.get("direction") # "increment" o "decrement"
    if direction not in ("increment", "decrement"):
      return Response(
        {"detail": "direction debe ser 'increment' o 'decrement'."},
        status=status.HTTP_400_BAD_REQUEST,
      )

    target = habit.target_per_period or 1

    with transaction.atomic():
      record = services.get_or_create_today_record(habit, request.user, today)

      if direction == "increment":
        record.progress = min(record.progress + 1, target)
      else:
        record.progress = max(record.progress - 1, 0)

      result = services.set_day_completed(habit, record, record.progress >= target, today)
      if not result.changed:
        # set_day_completed solo guarda si cambia el estado; el contador hay que guardarlo igual
        record.save(update_fields=["progress"])

    return self._completion_response(habit, record, result, today)

  @action(detail=False, methods=["get"], url_path="today")
  def today(self, request):
    """
    Estado del día de cada hábito. Es SOLO LECTURA: ausencia de registro = no completado.
    Hace un número FIJO de consultas (no crece con los hábitos): hábitos con su categoría,
    días completados, registros de hoy, progresos y bonus del periodo.
    """
    user = request.user
    today = timezone.localdate()

    habits = list(Habit.objects.filter(user=user).select_related("category"))
    if not habits:
      return Response([])

    days_by_habit = services.get_completed_days_by_habit(user)

    todays_records = {}
    for record in HabitRecord.objects.filter(habit__user=user, date__date=today).order_by("pk"):
      todays_records.setdefault(record.habit_id, record)

    progress_by_habit = {
      p.habit_id: p for p in Progress.objects.filter(user=user, habit__isnull=False)
    }

    # Los bonus del periodo en curso: una semana o un mes empiezan a lo sumo 31 días atrás
    bonuses = {
      (b.habit_id, b.frequency, b.period_start): b
      for b in PeriodBonus.objects.filter(
        habit__user=user, period_start__gte=today - timedelta(days=31)
      )
    }

    yesterday = today - timedelta(days=1)
    data = []
    for habit in habits:
      days = days_by_habit.get(habit.id, set())
      period = services.period_status(days, habit.frequency, habit.target_per_period, today)
      record = todays_records.get(habit.id)
      progress = progress_by_habit.get(habit.id)
      bonus = bonuses.get((habit.id, habit.frequency, period.period_start))

      data.append({
        "id": habit.id,
        "name": habit.name,
        "description": habit.description,
        "frequency": habit.frequency,
        "completed_today": today in days,
        "yesterday_completed": yesterday in days,
        "current_streak": period.streak_times,
        "target_per_period": habit.target_per_period,
        "current_progress": record.progress if record else 0,
        "week_history": services.week_history_flags(days, today),
        "category": {
          "id": habit.category.id if habit.category else None,
          "name": habit.category.name if habit.category else None,
          "color": habit.category.color if habit.category else None,
        },
        "progress": ProgressSerializer(progress).data if progress else None,
        # Estado del periodo, calculado en el backend (el frontend solo lo pinta)
        "period": {
          "start": period.period_start.isoformat(),
          "end": period.period_end.isoformat(),
        },
        "period_target": period.period_target,
        "days_done": period.days_done,
        "period_met": period.period_met,
        "streak_times": period.streak_times,
        "streak_periods": period.streak_periods,
        "at_risk": period.at_risk,
        "bonus_earned": (
          {"xp_habit": bonus.xp_habit, "xp_global": bonus.xp_global} if bonus else None
        ),
      })

    return Response(data)

#--------------------------------------------------------
# 👤 Registro de usuarios
#--------------------------------------------------------
class RegisterViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
  """Solo permite crear usuarios (POST). Sin list/retrieve/update/delete."""
  serializer_class = RegisterSerializer
  permission_classes = [permissions.AllowAny]

#--------------------------------------------------------
#  😎 Progreso / experiencia (SOLO LECTURA: el XP lo calcula el servidor)
#--------------------------------------------------------
class ProgressViewSet(mixins.ListModelMixin,
                      mixins.RetrieveModelMixin,
                      viewsets.GenericViewSet):
  serializer_class = ProgressSerializer
  permission_classes = [permissions.IsAuthenticated]

  def get_queryset(self):
    """
    Filtra el progreso solo del usuario autenticado.
    Si se pasa el id del hábito, filtra por ese hábito
    """
    user = self.request.user
    habit_id = self.request.query_params.get('habit_id')

    if habit_id:
      return Progress.objects.filter(user=user, habit_id=habit_id)

    return Progress.objects.filter(user=user, habit=None)
  
  def list(self, request, *args, **kwargs):
    """
    Si no se pasa habit_id, devuelve el progreso global.
    """
    queryset = self.get_queryset()
    if queryset.exists():
      serializer = self.get_serializer(queryset, many=True)
      return Response(serializer.data)

    return Response({"detail": "No hay progreso registrado."}, status=status.HTTP_404_NOT_FOUND)
  
  def retrieve(self, request, *args, **kwargs):
    """
    Obtiene un progreso específico (por id).
    """
    instance = self.get_object()
    serializer = self.get_serializer(instance)
    return Response(serializer.data)

  @action(detail=False, methods=["get"], url_path='global')
  def global_progress(self, request):
    """
    Endpoint: /api/progress/global/
    Devuelve el progreso global. Si el usuario aún no tiene, responde con los
    valores por defecto (nivel 1, 0 XP) SIN escribir en la BD.
    """
    progress = Progress.objects.filter(user=request.user, habit=None).first()
    if progress is None:
      progress = Progress(user=request.user, habit=None)
    data = self.get_serializer(progress).data
    data['current_streak'] = request.user.current_streak()
    data['monthly'] = request.user.monthly_completion_rate()
    return Response(data)

  @action(detail=True, methods=['get'], url_path='habit-progress')
  def habit_progress(self, request, pk=None):
    """
    Endpoint: /api/progress/<habit_id>/habit-progress/
    Devuelve el progreso de un hábito del usuario autenticado (solo lectura).
    Si el hábito no existe o es de otro usuario: 404
    Si aún no tiene progreso: 200 con valores por defecto, sin escribir en la BD
    """
    # 1. El hábito debe ser del usuario: la restricción va EN la consulta
    habit = get_object_or_404(Habit, pk=pk, user=request.user)

    # 2. Solo lectura: filter().first() en lugar de get_or_create
    progress = Progress.objects.filter(user=request.user, habit=habit).first()

    # 3. Sin progreso todavía es un estado válido: objeto en memoria, sin save()
    if progress is None:
      progress = Progress(user=request.user, habit=habit)

    # 4. Serializer y devolver
    return Response(self.get_serializer(progress).data)