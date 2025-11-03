from rest_framework import viewsets, permissions, status, generics
from rest_framework.exceptions import PermissionDenied
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from datetime import datetime, time
from django.db.models import Q
from django.contrib.auth import get_user_model
from .models import Habit, HabitRecord, CustomUser, Category, Progress
from .serializers import HabitSerializer, HabitRecordSerializer, RegisterSerializer, CategorySerializer, ProgressSerializer

# Create your views here.


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
  
  def perform_create(self, serializer):
    serializer.save(user=self.request.user)

  def update(self, request, *args, **kwargs):
    """Evita que al editar se reinicien campos no enviados."""
    kwargs['partial'] = True  # 👈 Forzamos PATCH siempre
    return super().update(request, *args, **kwargs)

  @action(detail=True, methods=["post"], url_path="toggle-completion")
  def toggle_completion(self, request, pk=None):
    habit = self.get_object()
    user = request.user
    today = timezone.localdate()
    note = request.data.get("note", "")

    # Aseguramos que haya un registro único por día
    record = HabitRecord.objects.filter(
      habit=habit, user=request.user, date__date=today
    ).first()

    if not record:
      record = HabitRecord.objects.create(
        habit=habit,
        user=request.user,
        date=timezone.make_aware(datetime.combine(today, time(0, 0))),
        completed=False,
      )

    # Actualiza el estado de completado según lo enviado desde el cliente
    completed = request.data.get("completed", None)
    if completed is not None:
      record.completed = bool(completed)

    if note is not None:
      record.note = note

    record.save()

    serializer = HabitRecordSerializer(record)
    return Response(serializer.data, status=status.HTTP_200_OK)

  @action(detail=False, methods=["get"], url_path="today")
  def today(self, request):
    """
    Devuelve los hábitos del usuario con su registro diario.
    Si no existe, lo crea una sola vez por día (sin duplicar).
    """
    today = timezone.localdate()
    habits = Habit.objects.filter(user=request.user)

    for habit in habits:
      # Garantiza que solo exista un registro por hábito y fecha
      HabitRecord.objects.get_or_create(
        habit=habit,
        user=request.user,
        date__date=today,  # compara solo la parte de la fecha
        defaults={
          "date": timezone.make_aware(datetime.combine(today, time(0, 0))),
          "completed": False,
        },
      )

    # Prepara la respuesta
    data = []
    for habit in habits:
      record = HabitRecord.objects.filter(
        habit=habit, user=request.user, date__date=today
      ).first()
      data.append({
        "id": habit.id,
        "name": habit.name,
        "description": habit.description,
        "completed_today": record.completed if record else False,
        "category": {
          "id": habit.category.id if habit.category else None,
          "name": habit.category.name if habit.category else None,
          "color": habit.category.color if habit.category else None,
        },
      })

    return Response(data)
  
#--------------------------------------------------------
# ⏱️ Registros de hábitos
#--------------------------------------------------------
class HabitRecordViewSet(viewsets.ModelViewSet):
  """CRUD de registros de hábitos."""
  serializer_class = HabitRecordSerializer
  permission_classes = [permissions.IsAuthenticated]

  # Solo registros que el hábitos del usuario autenticado
  def get_queryset(self):
    return HabitRecord.objects.filter(habit__user=self.request.user)
  
  # Verifica que el hábito pertenezca al usuario autenticado
  def perform_create(self, serializer):
    habit = serializer.validated_data.get("habit")

    # Previene que un usuario cree records en hábitos de otro user 
    if habit.user != self.request.user:
      raise PermissionDenied("No puedes registrar hábitos de otro usuario.")
    
    serializer.save(user=self.request.user)

    
    

#--------------------------------------------------------
# 👤 Registro de usuarios
#--------------------------------------------------------
class RegisterViewSet(viewsets.ModelViewSet):
  User = get_user_model()
  queryset = CustomUser.objects.all()
  permission_classes = [permissions.AllowAny]
  serializer_class = RegisterSerializer


#--------------------------------------------------------
#  😎 Registro de experiencia
#--------------------------------------------------------
class ProgressViewSet(viewsets.ModelViewSet):
  queryset = Progress.objects.all()
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
  
  @action(detail=False, methods=['get'], url_path='global')
  def global_progress(self, request):
    """
    Endpoint: /api/progress/global/
    Crea o devuelve el progreso global del usuario.
    """
    progress, created = Progress.objects.get_or_create(user=request.user, habit=None)
    serializer = self.get_serializer(progress)
    return Response(serializer.data)
  
  @action(detail=True, methods=['get'], url_path='habit-progress')
  def habit_progress(self, request, pk=None):
    """
    Endpoint: /api/progress/habit-progress/<habit_id>/
    Devuelve o crea el progreso asociado a un hábito del usuario autenticado.
    """
    try:
      progress, created = Progress.objects.get_or_creted(user=request.user, habit_id=pk)
      serializer = self.get_serializer(progress)
      return Response(serializer.data)
    except Exception as e:
      return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
