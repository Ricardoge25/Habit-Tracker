from rest_framework import serializers
from .models import Habit, HabitRecord, CustomUser, Category, Progress
from django.utils import timezone
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError

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
  
  """ def update(self, instance, validated_data):
  
    #Cuando un hábito se marca como completado, actualiza la experiencia global del usuario.

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

    return instance """

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
  progress = serializers.SerializerMethodField()
  
  class Meta:
    model = Habit
    fields = [
      "id", "name", "description", "frequency",
      "target_per_period", "category", "category_id",
      "created_at", "completed_today", 'progress'
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
  
  def get_progress(self, obj):
    user = self.context['request'].user
    progress = Progress.objects.filter(user=user, habit=obj).first()
    if progress:
      return ProgressSerializer(progress).data 
    return None

class RegisterSerializer(serializers.ModelSerializer):
  email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
  password = serializers.CharField(write_only=True)

  class Meta:
    model = CustomUser
    fields = ["id", "username", "email", "password"]

  def to_internal_value(self, data):
    # Normalizamos ANTES de que DRF valide: "" o " " -> None.
    # Si lo dejáramos para validate_email, DRF nunca lo ejecutaría con "".
    data = data.copy()
    email = data.get("email")
    if isinstance(email, str):
      email = email.strip().lower()
      data["email"] = email or None
    return super().to_internal_value(data)

  def validate_email(self, value):
    # Aquí value ya es None o un email normalizado
    if value is None:
      return None
    # Al declarar el campo a mano, DRF pierde el UniqueValidator automático,
    # así que lo hacemos explícito (el email ya viene en minúsculas).
    if CustomUser.objects.filter(email__iexact=value).exists():
      raise serializers.ValidationError("Ya existe una cuenta con este correo.")
    return value

  def validate(self, attrs):
    # Usuario "en memoria" para que UserAttributeSimilarityValidator
    # rechace contraseñas parecidas al username o al email.
    candidate = CustomUser(username=attrs.get("username"), email=attrs.get("email"))
    try:
      validate_password(attrs["password"], user=candidate)
    except DjangoValidationError as e:
      raise serializers.ValidationError({"password": list(e.messages)})
    return attrs

  def create(self, validated_data):
    return CustomUser.objects.create_user(**validated_data)

class ProgressSerializer(serializers.ModelSerializer):
  xp_to_next = serializers.SerializerMethodField()

  class Meta:
    model = Progress
    fields = ['habit', 'level', 'experience', 'xp_to_next']
    read_only_fields = fields

  def get_xp_to_next(self, obj):
    # ejemplo: cada nivel requiere 100 XP adicionales al anterior
    base_xp = 100
    return base_xp * obj.level
