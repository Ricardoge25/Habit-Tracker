from django.contrib import admin
from .models import Habit, HabitRecord, CustomUser, Category

# Register your models here.
admin.site.site_header = "HabitTracker Admin"
admin.site.site_title = "Habit Tracker Admin Portal"
admin.site.index_title = "Welcome to the HabitTracker Admin"

@admin.register(Habit)
class HabitAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'category', 'frequency', 'created_at')
    list_filter = ('user', 'category', 'frequency')
    search_fields = ('name', 'description')

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
    

admin.site.register(HabitRecord)
admin.site.register(CustomUser)
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "color", "created_at")  # 👈 esto muestra el usuario en la tabla
    list_filter = ("user",)                   # permite filtrar por usuario en el lateral
    search_fields = ("name", "user__username") # agrega búsqueda por nombre o usuario


#admin.site.register(Goal)
