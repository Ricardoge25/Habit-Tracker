from rest_framework import viewsets, permissions
from rest_framework.exceptions import PermissionDenied
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
    #Cada usuario ve solo sus hábitos 
    return Habit.objects.filter(user=self.request.user)
  
  # El hábito se crea asociado al usuario autenticado
  def perform_create(self, serializer):
    # Forzar que el hábito pertenezca al usuario autenticado
    serializer.save(user=self.request.user)


class HabitRecordViewSet(viewsets.ModelViewSet):
  """CRUD de registros de hábitos."""
  serializer_class = HabitRecordSerializer
  permission_classes = [permissions.IsAuthenticated]

  # Solo registros que el hábitos del usuario autenticado
  def get_queryset(self):
    return HabitRecord.objects.filter(habit__user=self.request.user)
  
  # Verifica que el hábito pertenezca al usuario autenticado
  def perform_crate(self, serializer):
    habit = serializer.validated_data("habit")
    # Previene que un usuario cree records en hábitos de otro user 
    if habit.user != self.request.user:
      raise PermissionDenied("No puedes registrar hábitos de otro usuario.")
    serializer.save()
    