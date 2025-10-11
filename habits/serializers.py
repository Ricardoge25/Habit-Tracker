from rest_framework import serializers
from .models import Habit, HabitRecord, CustomUser, Category

class CategorySerializer(serializers.ModelSerializer):
  class Meta:
    model = Category
    fields = ["id", "name", "color"]

class HabitRecordSerializer(serializers.ModelSerializer):
  habit_name = serializers.ReadOnlyField(source="habit.name")

  class Meta:
    model = HabitRecord
    fields = ["id", "date", "completed", "note"]

class HabitSerializer(serializers.ModelSerializer):
  category = CategorySerializer(read_only=True)
  category_id = serializers.PrimaryKeyRelatedField(
    source="category",
    queryset=Category.objects.none(),
    write_only=True,
    allow_null=True,
    required=False
  )
  records = HabitRecordSerializer(many=True, read_only=True)

  class Meta:
    model = Habit
    fields = [
      "id", "name", "description", "frequency",
      "target_per_period", "category", "category_id",
      "created_at", "records"
    ]
    extra_kwargs = {'category': {'allow_null': True, 'required': False}}

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    request = self.context.get("request")
    if request and hasattr(request, "user"):
      self.fields["category_id"].queryset = Category.objects.filter(user=request.user)

  
class RegisterSerializer(serializers.ModelSerializer):
  class Meta:
    model = CustomUser
    fields = ['id', 'username', 'email', 'password']
    extra_kwargs = {'password': {'write_only': True}}
    email = serializers.EmailField(required=False)

  def create(self, validated_data):
    user = CustomUser.objects.create_user(**validated_data)
    return user
  
""" 
class CategorySerializer(serializers.ModelSerializer):
  class  """

