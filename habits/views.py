from rest_framework import viewsets, permissions, status, generics
from rest_framework.exceptions import PermissionDenied
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from django.contrib.auth import get_user_model
from .models import Habit, HabitRecord, CustomUser, Category
from .serializers import HabitSerializer, HabitRecordSerializer, RegisterSerializer, CategorySerializer

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
  """CRUD de hábitos del usuario autenticado."""
  serializer_class = HabitSerializer
  permission_classes = [permissions.IsAuthenticated]

  """ Devuelve los hábitos del usuario autenticado"""
  def get_queryset(self):
    #Cada usuario ve solo sus hábitos 
    return Habit.objects.filter(user=self.request.user)
  
  """El hábito se crea asociado al usuario autenticado"""
  def perform_create(self, serializer):
    # Forzar que el hábito pertenezca al usuario autenticado
    serializer.save(user=self.request.user)

  # ⚙️ Acción personalizada para marcar como completado o no.
  @action(detail=True, methods=["post"], url_path="toggle-completion")
  def toggle_completion(self, request, pk=None):
    habit = self.get_object()

    # Fecha (por defecto: hoy)
    date = request.data.get("date") or timezone.localdate()
    completed = request.data.get("completed", True)
    note = request.data.get("note", "")

    record, created = HabitRecord.objects.get_or_create(
      habit=habit,
      date=date,
      defaults={
        "completed": completed,
        "note": note,
        "user": request.user,
      },
    )
    
    # Si ya existía, actualizamos su estado 
    if not created:
      record.completed = completed
      record.note = note
      record.save()

    serializer = HabitRecordSerializer(record)
    return Response(serializer.data, status=status.HTTP_200_OK)
  
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

