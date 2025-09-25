from rest_framework import serializers
from .models import Habit, HabitRecord


class HabitSerializer(serializers.ModelSerializer):
  completion_rate = serializers.SerializerMethodField()
  current_streak = serializers.SerializerMethodField()

  class Meta:
    model = Habit
    fields = [
      "id", "name", "description", "frequency", "target_per_period",
      "created_at", "updated_at", "completion_rate", "current_streak"
    ]

  def get_completion_rate(self, obj):
    return obj.completion_rate(days=30)
  
  def get_current_streak(sel, obj):
    return obj.current_streak()
  

class HabitRecordSerializer(serializers.ModelSerializer):
  habit_name = serializers.ReadOnlyField(source="habit.name")

  class Meta:
    model = HabitRecord
    fields = '__all__'