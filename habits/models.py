from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth.models import AbstractUser

class CustomUser(AbstractUser):
  """Modelo de usuario personalizado (si se necesitan campos extra en el futuro)"""
  email = models.EmailField(unique=True, null=True, blank=True)

  def __str__(self):
    return self.username

class Category(models.Model):
  """ Categorias opcionales para agrupar hábitos """
  user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="categories") #Relación con el usuario
  name = models.CharField(max_length=60) #Nombre de la categoría 
  color = models.CharField(max_length=7, blank=True, null=True, default='#0003A3') # color hexadecimal
  created_at = models.DateTimeField(auto_now_add=True) #Campo para la fecha de creación

  class Meta:
    unique_together = ("user", "name") # Evita que un mismo usuario cree dos categorías con el mismo nombre
    ordering = ["name"] #Ordenamiento alfabéticamente

  def __str__(self):
    return self.name # Devuelve el nombre 

class Habit(models.Model):
  """Modelo principal para un hábito"""

  # Diccionario con los periodos de frecuencia para los hábitos 
  FREQUENCY_CHOICES = [
    ("daily", "Diario"),
    ("weekly", "Semanal"),
    ("monthly", "Mensual"),
  ]

  #Relación con el usuario
  user = models.ForeignKey(
    settings.AUTH_USER_MODEL, 
    on_delete=models.CASCADE, 
    related_name="habits"
  ) 
  name = models.CharField(max_length=150) # Nombre del hábito
  slug = models.SlugField(max_length=160, blank=True, null=True) #Para las URLS
  description = models.TextField(blank=True, null=True) #Descripción del hábito
  #Relación con la categoría 
  category = models.ForeignKey(
    Category, 
    on_delete=models.SET_NULL, 
    null=True,
    blank=True,
    related_name="habits",
    default=None,
  )
  # Campo para la frecuencia
  frequency = models.CharField(
    max_length=10,
    choices=FREQUENCY_CHOICES, 
    default="daily"
  )
  # Objetivo por periodo
  target_per_period = models.PositiveSmallIntegerField(
    default=1,
    help_text="Cuántas veces debería completarse por periodo (ej: 1 vez al día)"
  ) 
  """ reminder_time = models.TimeField(blank=True, null=True) #Hora sugerida para recordatorio """
  """ is_active = models.BooleanField(default=True) #Estado del hábito """
  """ skip_allowed = models.PositiveSmallIntegerField(default=0,
      help_text="Días permitidos de salto por periodo (opcional, para no romper la racha)") #Campo para saltar o no el hábito """
  created_at = models.DateTimeField(auto_now_add=True) #Fecha de creación
  updated_at = models.DateTimeField(auto_now=True) #Fecha de modificación

  class Meta:
    unique_together = ("user", "name") # Evita duplicados por usuario con el mismo nombre del hábito
    """indexes = [
      models.Index(fields=["user", "name"]), # Para búsquedas
    ]"""
    ordering = ["-created_at"]

  def __str__(self):
    return f"{self.name} ({self.user})"
  
  #----------------------------------------------------
  # Operaciones / utilidades para los hábitos
  #----------------------------------------------------
  def mark(self, when=None, completed=True, note=None):
    """
    Marca el hábito como completado o no en una fecha.
    """
    if when is None:
      when = timezone.localdate()
    record, created = HabitRecord.objects.get_or_create(
      habit=self,
      date=when,
      defaults={"completed": bool(completed), "note": note or ""}
    )
    if not created:
      record.completed = bool(completed)
      if note is not None:
        record.note = note
      record.save()
    return record
  

  """# Devuelve un QuerySet filtrado de registros en un rango de fechas
  def get_records_qs(self, start=None, end=None):
    qs = self.records.all()
    if start:
      qs = qs.filter(date__gte=start)
    if end:
      qs = qs.filter(date__lte=end)
    return qs"""
  

  """def completed_dates_set(self, start=None, end=None):
    #Retorna un set() de dates completadas en el rango dado
    qs = self.get_records_qs(start=start, end=end).filter(completed=True).values_list("date", flat=True)
    return set(qs)""" 
    

  def completion_rate(self, days=30, upto=None):
    """% de cumplimiento en los últimos `days` días."""
    if upto is None:
      upto = timezone.localdate()
    start = upto - timedelta(days=days - 1)
    total_days = days if days > 0 else 0
    if total_days == 0:
      return 0.0
    completed_count = self.records.filter(
      date__range=(start, upto),
      completed=True
    ).count()
    return round((completed_count / total_days) * 100, 2)
  

  def current_streak(self, upto=None):
    """Cuenta de días consecutivos completados hasta 'upto'."""
    if upto is None:
      upto = timezone.localdate()
    completed = set(
      self.records.filter(completed=True, date__lte=upto)
      .values_list("date", flat=True)
    )
    streak = 0
    d = upto
    while d in completed:
      streak += 1
      d = d - timedelta(days=1)
    return streak
  

  """ def longest_streak(self, start=None, end=None):
    
    #Calcula la racha más larga en el intervalo [start, end].
    #Si no se pasan fechas, revisa TODOS los registros.
  
    completed_qs = self.get_records_qs(start=start, end=end).filter(completed=True).values_list("date", flat=True)
    dates = sorted(list(completed_qs))
    longest = 0
    current = 0
    prev = None
    for dt in dates:
      if prev is None or (dt - prev).days == 1:
        current += 1
      else:
        current = 1
      if current > longest:
        longest = current
      prev = dt
    return longest """
  

class HabitRecord(models.Model):
  """Registro de cumplimiento de un hábito en una fecha"""

  #Relación 1:N con el hábito
  habit = models.ForeignKey(
    Habit, 
    on_delete=models.CASCADE, 
    related_name="records") 
  date = models.DateField() #Fecha
  completed = models.BooleanField(default=False) # Completado o no
  note = models.TextField(blank=True, null=True) # Nota o comentario
  created_at = models.DateTimeField(auto_now_add=True) # Fecha de creación

  class Meta:
    unique_together = ("habit", "date") # Evita duplicados para el mismo día
    ordering = ["-date"] # Ordenamiento por fechas
    indexes = [
      models.Index(fields=["habit", "date"]), # Optimiza consultas por rangos de fecha
    ]

  def __str__(self): # Devuelve un String con nombre del hábito, fecha y check
    return f"{self.habit.name} - {self.date} - {'✅' if self.completed else '❌'}" 
  

# DEFINIR METAS ASOCIADAS A UN HÁBITO
""" class Goal(models.Model):
  #Objetivo que puede vincularse a un hábito (por ejemplo: '80% en 30 días').
  user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="goals") # Relación con el usuario
  habit = models.ForeignKey(Habit, on_delete=models.CASCADE, related_name="goal", null=True, blank=True) # Relación con el hábito
  title = models.CharField(max_length=150) # Título de la meta
  description = models.TextField(blank=True, null=True) # Descripción de la meta
  start_date = models.DateField() # Fecha de inicio
  end_date = models.DateField() # Fecha de terminación
  target_percent = models.PositiveSmallIntegerField(default=75) # ej: 75%
  achieved = models.BooleanField(default=False) # ¿Conseguido?
  created_at = models.DateTimeField(auto_now_add=True) # Fecha de creación

  # Calcula el porcentaje real de cumplimiento de un hábito en el rango entre start_date y end_date
  def progress_percent(self):
    days = (self.end_date - self.start_date).days + 1
    if days <= 0:
      return 0.0
    if self.habit:
      completed = self.habit.get_records_qs(start=self.start_date, end=self.end_date).filter(completed=True).count()
      return round((completed / days) * 100, 2)
    return 0.0
  

  # Marca achieve=True si el progreso es >= al porcentaje del objetivo
  def check_achieved(self):
    self.achieved = self.progress_percent() >= self.target_percent
    self.save()
    return self.achieved
  
  def __str__(self): # Devuelve el título de la meta
    return self.title """


