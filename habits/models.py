from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db.models.functions import TruncDate

# Tope de "días distintos por periodo" según la frecuencia (el diario no tiene).
# Viven a nivel del módulo para compartirlos con el serializer y con la constraint.
MAX_WEEKLY_TARGET = 5       # 6 - 7 días por semana ya es, en la práctica, un hábito diario.
MAX_MONTHLY_TARGET = 28     # febrero tiene 28 días: la meta es alcanzable en cualquier mes.
MAX_TARGET_BY_FREQUENCY = {
  "weekly": MAX_WEEKLY_TARGET,
  "monthly": MAX_MONTHLY_TARGET,
}

class CustomUser(AbstractUser):
  """Modelo de usuario personalizado (si se necesitan campos extra en el futuro)"""
  email = models.EmailField(unique=True, null=True, blank=True)

  def __str__(self):
    return self.username

  def save(self, *args, **kwargs):  
    if not self.email:
      self.email = None
    super().save(*args, **kwargs) 

  def current_streak(self, upto=None):  
    if upto is None:
      upto = timezone.localdate()

    completed_days = set(
      self.habitrecord_set.filter(completed=True, date__date__lte=upto)
      .annotate(day=TruncDate("date"))
      .values_list("day", flat=True)
    )

    streak = 0
    consecutive_misses = 0
    d = upto

    while True:
      if d in completed_days:
        streak += 1
        consecutive_misses = 0
      else:
        consecutive_misses += 1
        if consecutive_misses >= 2:
          break

      d -= timedelta(days=1)

    return streak
  
  def monthly_completion_rate(self, upto=None):
    """% de días al mes (hasta hoy) con al menos un hábito completado."""
    if upto is None:
      upto = timezone.localdate()

    start = upto.replace(day=1)
    days_elapsed = (upto - start).days + 1

    completed_days = set(
      self.habitrecord_set.filter(completed=True, date__date__range=(start, upto))
      .annotate(day=TruncDate("date"))
      .values_list("day", flat=True)
    )

    percentage = round((len(completed_days) / days_elapsed) * 100, 2) if days_elapsed else 0.0

    return {
      "percentage": percentage,
      "completed_days": len(completed_days),
      "days_elapsed": days_elapsed,
    }

class Category(models.Model):
  """ Categorias opcionales para agrupar hábitos """
  user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="categories") #Relación con el usuario
  name = models.CharField(max_length=60, default="General") #Nombre de la categoría 
  color = models.CharField(max_length=7, blank=True, null=True, default='#4951E4') # color hexadecimal
  created_at = models.DateTimeField(auto_now_add=True) #Campo para la fecha de creación

  class Meta:
    unique_together = ("user", "name") # Evita que un mismo usuario cree dos categorías con el mismo nombre
    ordering = ["name"] #Ordenamiento alfabéticamente
    verbose_name = "Categoría"

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
    help_text="Cuántas veces debería completarse por periodo (ej: 1 vez al día)", 
    null=True
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
    verbose_name = "Hábito"
    constraints = [
      # Última línea de defensa: la BD rechaza una meta fuera de rango para la frecuencia.
      # (Un diario no tiene tope. Si target_per_period es NULL la constraint no lo rechaza:
      # en SQL un CHECK con NULL no es falso. NULL se interpreta como la meta por defecto.)
      # OJO: los valores 5 y 28 quedan escritos en la migración; cambiarlos exige otra migración.
      models.CheckConstraint(
        condition=(
          models.Q(frequency="daily")
          | models.Q(
            frequency="weekly",
            target_per_period__gte=1,
            target_per_period__lte=MAX_WEEKLY_TARGET,
          )
          | models.Q(
            frequency="monthly",
            target_per_period__gte=1,
            target_per_period__lte=MAX_MONTHLY_TARGET,
          )
        ), 
        name="habit_target_matches_frequency",
        violation_error_message="La meta n es válida para la frecuencia elegida.",
      ),
    ]

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
      defaults={"completed": bool(completed), "note": note or "", "user": self.user}
    )
    if not created:
      record.completed = bool(completed)
      if note is not None:
        record.note = note
      record.save()

    # ---------- SISTEMA DE EXPERIENCIA ----------
    if completed:
      xp_gain = 10 # XP base por hábito completado

      # Progreso específico del hábito (opcional)
      progress_habit, _ = Progress.objects.get_or_create(user=self.user, habit=self)
      progress_habit.add_experience(xp_gain)

      # Progreso global
      progress_global, _ = Progress.objects.get_or_create(user=self.user, habit=None)
      progress_global.add_experience(xp_gain)

    return record

  # Historial semanal
  def week_history(self, upto=None):
    """
    FEATURE: Historial semanal de puntitos.
    Devuelve una lista de 7 booleanos (últimos 7 días, terminando domingo)
    indicando si el hábito fue completado ese día
    """
    if upto is None:
      upto = timezone.localdate()
    start = upto - timedelta(days=6)

    completed_days = set(
      self.records.filter(completed=True, date__date__range=(start, upto))
      .annotate(day=TruncDate("date"))
      .values_list("day", flat=True)
    )

    history = []
    d = start
    while d <= upto:
      history.append(d in completed_days)
      d += timedelta(days=1)
    return history

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
    """
    Racha con tolerancia: un día aislado sin completar no rompe la racha,
    pero dos días consecutivos sin completar sí la rompe.
    """
    if upto is None:
      upto = timezone.localdate()

    completed_days = set(
      self.records.filter(completed=True)
      .annotate(day=TruncDate("date"))
      .values_list("day", flat=True)
    )

    streak = 0 
    consecutive_misses = 0
    d = upto

    # Si hoy aún no se completó, no se penaliza de inmediato:
    # el día no ha terminado, así que empieza a evaluar desde el día anterior.
    if d not in completed_days:
      d -= timedelta(days=1)

    while True:
      if d in completed_days:
        streak += 1
        consecutive_misses = 0
      else:
        consecutive_misses += 1
        if consecutive_misses >= 2:
          break # Dos fallos seguidos: racha termina aquí

      d -= timedelta(days=1)

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

  # Relación 1:N con el hábito
  habit = models.ForeignKey(
    Habit, 
    on_delete=models.CASCADE, 
    related_name="records") 
  date = models.DateTimeField(default=timezone.now) #Fecha
  completed = models.BooleanField(default=False) # Completado o no
  completed_at = models.DateTimeField(null=True, blank=True) 
  note = models.TextField(blank=True, null=True) # Nota o comentario
  progress = models.PositiveIntegerField(default=0) 

  # Ledger de XP: cuánto XP dio ESTE registro al completarse. Al desmarcar se resta
  # exactamente esto (no se recalcula): así editar la meta entre media no genera XP de más.
  xp_habit = models.PositiveIntegerField(default=0)
  xp_global = models.PositiveIntegerField(default=0)
  user = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,null=True, blank=True)

  class Meta:
    constraints = [
      models.UniqueConstraint(fields=['habit', 'date', 'user'], name='unique_habit_per_day')
    ]

  def __str__(self):
    return f"{self.habit.name} - {self.date} - {'Completado' if self.completed else 'Pendiente'} - {self.user}"
  
  def clean(self):
    if self.progress > self.habit.target_per_period:
      raise ValidationError("El progreso no puede superar la meta del hábito.")
  

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
  achieved = models.BooleanField(default=False) # ¿Conseguido?Ñ
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

class Progress(models.Model):
  """Sistema de progreso del usuario
    Puede representar el progreso global o el de un hábito en particular
  """
  user = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    on_delete=models.CASCADE,
    related_name="progress"
  )
  habit = models.ForeignKey(
    Habit,
    on_delete=models.CASCADE,
    null=True,
    blank=True,
    related_name="progress"
  )
  level = models.PositiveIntegerField(default=1)
  experience = models.PositiveIntegerField(default=0)
  created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
  updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

  def xp_to_next_level(self):
    # Fórmula cuadrática: se va volviendo más difícil con cada nivel que pasa
    return (self.level * 100)
  
  def add_experience(self, amount):
    """Suma experiencia y sube de nivel automáticamente si corresponde."""
    self.experience += amount
    
    while self.experience >= self.xp_to_next_level():
      self.experience -= self.xp_to_next_level()
      self.level += 1
    self.save()

  def remove_experience(self, amount):
    """
    Resta experiencia y, si hace falta, baja de nivel.
    Es el inverso exacto de add_experience: sumar X y luego restar X deja el
    nivel y la experiencia como estaban (así marcar/desmarcar no regala niveles).
    El mínimo es nivel 1 con 0 XP.
    """
    self.experience -= amount

    # "Pedir prestado" al nivel anterior mientras falte experiencia
    while self.experience < 0 and self.level > 1:
      self.level -= 1
      self.experience += self.xp_to_next_level()

    # En nivel 1 no hay nivel anterior: el piso es 0 XP
    self.experience = max(0, self.experience)
    self.save()

  def __str__(self):
    if self.habit:
      return f"{self.user.username} - {self.habit.name}"
    return f"{self.user.username} (Global)"
  
  class Meta:
    verbose_name = "Progreso"
    verbose_name_plural = "Progresos"
    constraints = [
      # Un progreso por (usuario, hábito) cuando hay hábito
      models.UniqueConstraint(
        fields=["user", "habit"],
        condition=models.Q(habit__isnull=False),
        name="unique_progress_per_user_habit",
      ),
      # UN solo progreso global por usuario. unique_together no lo cubre
      # porque en SQL NULL != NULL.
      models.UniqueConstraint(
        fields=["user"],
        condition=models.Q(habit__isnull=True),
        name="unique_global_progress_per_user",
      ),
    ]

class PeriodBonus(models.Model):
  """
  Bonus de XP por cumplir la meta de un periodo (semana o mes) de un hábito.

  Una fila significa: "este hábito YA cobró el bonus de este periodo."
  Guarda cuánto XP se dio, para poder revocar exactamente esa cantidad si el 
  usuario desmarca y vuelve a quedar por debajo de la meta (aunque la fórmula
  del bonus cambie después). No lleva `user`: ya se deriva de `habit.user`, y 
  duplicarlo permitiría datos inconsistentes.
  """
  # Un hábito diario no tiene bonus de periodo: ya cobra XP cada día
  BONUS_FREQUENCY_CHOICES = [
    ("weekly", "Semanal"),
    ("monthly", "Mensual"),
  ]

  habit = models.ForeignKey(
    Habit,
    on_delete=models.CASCADE,
    related_name="period_bonuses"
  )
  # Frecuencia con la que se cobró. Forma parte de la unicidad porque un lunes puede
  # ser a la vez inicio de semana y día 1 del mes (ej. 1-feb-2027): sin ella, un hábito
  # que pasa de semanal a mensual chocaría con su propio bonus.
  frequency = models.CharField(max_length=10, choices=BONUS_FREQUENCY_CHOICES)
  # Lunes de la semana (o día 1 del mes). DateField y no DateTimeField: un periodo
  # es una fecha de calendario, y así se evitan los problemas de zona horaria.
  period_start = models.DateField()
  # Meta vigente cuando se cobró. Sirve para decidir si hay que revocarlo al desmarcar,
  # aunque el usuario edite la meta a mitad del periodo.
  target = models.PositiveSmallIntegerField()
  xp_habit = models.PositiveIntegerField()   # XP otorgado al progreso del hábito
  xp_global = models.PositiveIntegerField()  # XP otorgado al progreso global
  created_at = models.DateTimeField(auto_now_add=True)

  class Meta:
    verbose_name = "Bonus de periodo"
    verbose_name_plural = "Bonus de periodo"
    ordering = ["-period_start"]
    constraints = [
      # Garantiza que el bonus se cobre UNA sola vez por hábito, frecuencia y periodo,
      # incluso si llegan dos peticiones simultáneas.
      models.UniqueConstraint(
        fields=["habit", "frequency", "period_start"],
        name="unique_bonus_per_habit_frequency_period",
      ),
      # `choices` solo se valida en formularios; esto lo garantiza en la BD
      models.CheckConstraint(
        condition=models.Q(frequency__in=["weekly", "monthly"]),
        name="period_bonus_frequency_not_daily",
      ),
    ]

  def __str__(self):
    return f"{self.habit.name} - {self.frequency} - {self.period_start}"