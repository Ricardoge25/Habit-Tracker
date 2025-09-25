from rest_framework import viewsets, permissions
from .models import Habit, HabitRecord
from .serializers import HabitSerializer, HabitRecordSerializer

# Create your views here.
class HabitViewSet(viewsets.ModelViewSet):
  """CRUD de hábitos del usuario autenticado."""
  queryset = Habit.objects.all()
  serializer_class = HabitSerializer
  permission_classes = [permissions.IsAuthenticated]

  # Devuelve los hábitos del usuario autenticado
  def get_queryset(self):
    user = self.request.user
    if user.is_authenticated:
      return Habit.objects.filter(user=user)
    return Habit.objects.all()  # 🔓 solo mientras pruebas
  
  # El hábito se crea asociado al usuario autenticado
  def perform_create(self, serializer):
    serializer.save(user=self.request.user)
    serializer.save()


class HabitRecordViewSet(viewsets.ModelViewSet):
  """CRUD de registros de hábitos."""
  serializer_class = HabitRecordSerializer
  permission_classes = [permissions.IsAuthenticated]

  # Solo registros que el hábitos del usuario autenticado
  def get_queryset(self):
    return HabitRecord.objects.filter(habit__user=self.request.user)
  
  # Verifica que el hábito pertenezca al usuario autenticado
  def perform_crate(self, serializer):
    habit = serializer.validated_data["habit"]
    if habit.user != self.request.user:
      raise permissions.PermissionDenied("No puedes registrar hábitos de otro usuario.")
    serializer.save()
    