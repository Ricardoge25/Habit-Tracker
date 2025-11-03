from rest_framework import serializers
from .models import Habit, HabitRecord, CustomUser, Category, Progress
from django.utils import timezone

class CategorySerializer(serializers.ModelSerializer):
  habit_count = serializers.SerializerMethodField()

  class Meta:
    model = Category
    fields = ["id", "name", "color", "habit_count"]

  def get_habit_count(self, obj):
    return obj.habits.count()
  
  def validate(self, data):
    user = self.context['request'].user
    name = data.get('name')

    # Base queryset para este usuario
    qs = Category.objects.filter(user=user, name__iexact=name)

    # Si se actualiza, excluye la categoría actual
    if self.instance:
      qs = qs.exclude(pk=self.instance.pk)

    if qs.exists():
      raise serializers.ValidationError(
        {"name" : "Ya tiene una categoría con ese nombre."}
      )
    
    return data

class HabitRecordSerializer(serializers.ModelSerializer):
  habit_name = serializers.CharField(source="habit.name", read_only=True)

  class Meta:
    model = HabitRecord
    fields = "__all__"
    read_only_fields = ["user"]

  def validate_progress(self, value):
    habit = self.initial_data.get("habit")
    if habit and value:
      habit_obj = Habit.objects.get(id=habit)
      if value > habit_obj.target_per_period:
        raise serializers.ValidationError("El progreso no puede superar la meta del hábito")
      
    return value
  
  def update(self, instance, validated_data):
    """
    Cuando un hábito se marca como completado, actualiza la experiencia global del usuario.
    """
    user = self.context["request"].user
    completed_before = instance.completed # estado anterior
    instance = super().update(instance, validated_data)

    # Si el usuario lo acaba de completar (de False a True)
    if not completed_before and instance.completed:
      from .models import Progress

      # progreso global (habit=None)
      global_progress, _ = Progress.objects.get_or_create(user=user, habit=None)
      global_progress.add_experience(25) # XP global

      # progreso independiente de cada hábito
      habit_progress, _ = Progress.objects.get_or_create(user=user, habit=instance.habit)
      habit_progress.add_experience(10) # XP por hábito 

    return instance


class HabitSerializer(serializers.ModelSerializer):
  category = CategorySerializer(read_only=True)
  category_id = serializers.PrimaryKeyRelatedField(
    source="category",
    queryset=Category.objects.none(),
    write_only=True,
    allow_null=True,
    required=False
  )
  completed_today = serializers.SerializerMethodField()

  class Meta:
    model = Habit
    fields = [
      "id", "name", "description", "frequency",
      "target_per_period", "category", "category_id",
      "created_at", "completed_today",
    ]
    extra_kwargs = {'category': {'allow_null': True, 'required': False}}

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    request = self.context.get("request")
    if request and hasattr(request, "user"):
      self.fields["category_id"].queryset = Category.objects.filter(user=request.user)

  def get_completed_today(self, obj):
    """Devuelve si el hábito está completado hoy."""
    today = timezone.localdate()
    return obj.records.filter(date=today, completed=True).exists()

class RegisterSerializer(serializers.ModelSerializer):
  class Meta:
    model = CustomUser
    fields = ['id', 'username', 'email', 'password']
    extra_kwargs = {'password': {'write_only': True}}
    email = serializers.EmailField(required=False)

  def create(self, validated_data):
    user = CustomUser.objects.create_user(**validated_data)
    return user
  
class ProgressSerializer(serializers.ModelSerializer):
  xp_to_next = serializers.SerializerMethodField()

  class Meta:
    model = Progress
    fields = ['id', 'user', 'habit', 'level', 'experience', 'xp_to_next']

  def get_xp_to_next(self, obj):
    # ejemplo: cada nivel requiere 100 XP adicionales al anterior
    base_xp = 100
    return base_xp * obj.level
