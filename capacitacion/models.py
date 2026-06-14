from django.db import models
from django.contrib.auth.models import User


class Tarea(models.Model):
    PRIORIDAD_CHOICES = [
        ('alta', 'Alta'),
        ('media', 'Media'),
        ('baja', 'Baja'),
    ]
    TIPO_CHOICES = [
        ('LLAMADA', 'Llamada'),
        ('PEDIDO', 'Pedido'),
        ('SEGUIM', 'Seguimiento'),
        ('REPORTE', 'Reporte'),
        ('TURNO', 'Turno'),
    ]

    orden = models.PositiveSmallIntegerField(default=0)
    hora = models.CharField(max_length=5)           # "08:00"
    mins = models.PositiveSmallIntegerField()        # 480
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    prioridad = models.CharField(max_length=5, choices=PRIORIDAD_CHOICES)
    flexible = models.BooleanField(default=False)
    nombre = models.CharField(max_length=200)
    habilidades = models.JSONField(default=list, blank=True)
    descripcion = models.TextField()
    pasos = models.JSONField(default=list)           # ["paso 1", "paso 2"]
    tips = models.JSONField(default=list, blank=True) # [{"k": "tip", "t": "texto"}]
    titulo_video = models.CharField(max_length=200, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ['orden', 'mins']
        verbose_name = 'Tarea'
        verbose_name_plural = 'Tareas'

    def __str__(self):
        return f"{self.hora} · {self.nombre}"


class Bloque(models.Model):
    label = models.CharField(max_length=100, unique=True)
    tareas = models.ManyToManyField(Tarea, through='BloqueTarea')
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['orden']
        verbose_name = 'Bloque'
        verbose_name_plural = 'Bloques'

    def __str__(self):
        return self.label


class BloqueTarea(models.Model):
    # related_name='bloquearea_set' → permite bloque.bloquearea_set.all() en plantillas/vistas
    bloque = models.ForeignKey(Bloque, on_delete=models.CASCADE, related_name='bloquearea_set')
    tarea = models.ForeignKey(Tarea, on_delete=models.CASCADE)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['orden']


class ProgresoTarea(models.Model):
    # related_name='progreso_set' → permite usuario.progreso_set.all() para consultar el progreso de un usuario
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='progreso_set')
    tarea = models.ForeignKey(Tarea, on_delete=models.CASCADE)
    completada = models.BooleanField(default=False)
    fecha = models.DateField(auto_now=True)

    class Meta:
        unique_together = ['usuario', 'tarea', 'fecha']
        verbose_name = 'Progreso'

    def __str__(self):
        return f"{self.usuario.username} · {self.tarea.nombre}"