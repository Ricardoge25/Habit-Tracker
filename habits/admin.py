from django.contrib import admin
from .models import Habit, HabitRecord

# Register your models here.

#admin.site.register(Category)
admin.site.register(Habit)
admin.site.register(HabitRecord)
#admin.site.register(Goal)