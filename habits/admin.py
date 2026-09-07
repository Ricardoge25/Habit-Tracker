from django.contrib import admin
from .models import Habit, HabitRecord, CustomUser, Category, Progress

# Register your models here.
admin.site.site_header = "HabitTracker Admin"
admin.site.site_title = "Habit Tracker Admin Portal"
admin.site.index_title = "Welcome to the HabitTracker Admin"

@admin.register(Habit)
class HabitAdmin(admin.ModelAdmin):
  list_display = ("name", "user", "category", "get_streak", "created_at")
  list_filter = ("frequency", "category", "user")
  search_fields = ("name", "description", "user__username")
  select_related = ("user", "category")

  @admin.display(description="Racha Actual")
  def get_streak(self, obj):
    return f"🔥 {obj.current_streak()} días"

  def formfield_for_foreignkey(self, db_field, request, **kwargs):
    if db_field.name == "category":
      # Caso 1: si estamos editando un hábito existente
      if hasattr(request, '_obj_') and request._obj_ is not None and request._obj_.user:
        kwargs["queryset"] = Category.objects.filter(user=request._obj_.user)
      # Caso 2: si estamos creando un nuevo hábito, filtramos por el usuario logueado
      else:
        kwargs["queryset"] = Category.objects.filter(user=request.user)
    return super().formfield_for_foreignkey(db_field, request, **kwargs)

  def get_form(self, request, obj=None, **kwargs):
    request._obj_ = obj  # Guardamos el objeto actual (o None si es nuevo)
    return super().get_form(request, obj, **kwargs)

@admin.register(HabitRecord)
class HabitRecordAdmin(admin.ModelAdmin):
  list_display = ("habit", "user", "date", "completed", "completed_at")
  list_filter = ("completed", "date", "user")
  search_fields = ("habit__name", "user__username")
  ordering = ("-date",)
  select_related = ("habit", "user")

@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
  list_display = ("username", "email", "get_global_streak", "is_staff")
  search_fields = ("username", "email")

  @admin.display(description="Racha Global")
  def get_global_streak(self, obj):
    return f"⚡ {obj.current_streak()} días"

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
  list_display = ("name", "user", "color", "created_at")  # 👈 esto muestra el usuario en la tabla
  list_filter = ("user",)                   # permite filtrar por usuario en el lateral
  search_fields = ("name", "user__username") # agrega búsqueda por nombre o usuario
  select_related = ("user",)

@admin.register(Progress)
class ProgressAdmin(admin.ModelAdmin):
  list_display = ("user", "get_progress_name", "level", "experience", "created_at", "updated_at")
  list_filter = ("level", "user", "habit")
  search_fields = ("user__username", "habit__name")
  ordering = ("-updated_at",)
  select_relate = ("user", "habit")

  @admin.display(description="Progreso Asignado")
  def get_progress_name(self, obj):
    return obj.habit.name if obj.habit else "Progreso Global"

#admin.site.register(Goal)
