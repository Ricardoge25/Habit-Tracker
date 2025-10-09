from django.contrib import admin
from .models import Habit, HabitRecord, CustomUser, Category

# Register your models here.
admin.site.site_header = "HabitTracker Admin"
admin.site.site_title = "Habit Tracker Admin Portal"
admin.site.index_title = "Welcome to the HabitTracker Admin"

@admin.register(Habit)
class HabitAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "category", "frequency", "created_at")
    list_filter = ("user",) 
    search_fields = ("name", "user__username")


    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # Si el campo es 'category', mostramos todas las categorías
        # porque el admin (tú) puede crear hábitos para cualquier usuario.
        if db_field.name == "category":
            kwargs["queryset"] = Category.objects.all()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
admin.site.register(HabitRecord)
admin.site.register(CustomUser)
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "color", "created_at")  # 👈 esto muestra el usuario en la tabla
    list_filter = ("user",)                   # permite filtrar por usuario en el lateral
    search_fields = ("name", "user__username") # agrega búsqueda por nombre o usuario


#admin.site.register(Goal)
