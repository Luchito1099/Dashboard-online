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


class Estrategia(models.Model):
    """Estrategia de venta que se puede asociar a un pedido (en Seguimiento).
    Se gestiona desde Capacitación › Estrategias (CRUD del admin)."""
    nombre = models.CharField(max_length=120)
    descripcion = models.CharField(max_length=300, blank=True)
    icono = models.CharField(max_length=10, blank=True)   # emoji
    activo = models.BooleanField(default=True)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['orden', 'nombre']
        verbose_name = 'Estrategia'
        verbose_name_plural = 'Estrategias'

    def __str__(self):
        return self.nombre


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


# ───────────────────────── Lecciones (mini-clases en video) ─────────────────────────

# Audiencias de la capacitación. 'general' la ve cualquiera; las demás coinciden con el
# rol del usuario (Perfil.rol). Constante reutilizable (también para el runbook a futuro).
AUDIENCIA_GENERAL = 'general'
AUDIENCIA_CHOICES = [
    (AUDIENCIA_GENERAL, 'General (todos)'),
    ('vendedor', 'Vendedor'),
    ('analista', 'Analista'),
    ('marketing', 'Marketing'),
]

import re


class Leccion(models.Model):
    """Mini-clase en video: título, objetivos, descripción, video embebido y un resumen
    ocultable. Segmentada por audiencia. El admin pega el link y se incrusta para todos."""
    titulo = models.CharField(max_length=200)
    audiencia = models.CharField(max_length=12, choices=AUDIENCIA_CHOICES, default=AUDIENCIA_GENERAL)
    objetivos = models.TextField(blank=True, help_text='Uno por línea.')
    descripcion = models.TextField(blank=True)
    video_url = models.CharField(max_length=500, blank=True, help_text='Link de YouTube o Vimeo.')
    resumen = models.TextField(blank=True, help_text='Resumen ocultable de la clase.')
    orden = models.PositiveSmallIntegerField(default=0)
    activo = models.BooleanField(default=True)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['orden', 'titulo']
        verbose_name = 'Lección'
        verbose_name_plural = 'Lecciones'

    def __str__(self):
        return self.titulo

    @property
    def objetivos_lista(self):
        return [o.strip() for o in (self.objetivos or '').splitlines() if o.strip()]

    @property
    def video_embed_url(self):
        """Convierte un link de YouTube/Vimeo a su URL embebible (o '' si no es válido).
        Mismo criterio que parseVideoUrl del runbook."""
        url = (self.video_url or '').strip()
        m = re.search(r'(?:youtube\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/)([\w-]{11})', url)
        if m:
            return f'https://www.youtube.com/embed/{m.group(1)}?rel=0'
        m = re.search(r'vimeo\.com/(?:video/)?(\d+)', url)
        if m:
            return f'https://player.vimeo.com/video/{m.group(1)}'
        return ''


class AccesoLeccion(models.Model):
    """Registro de quién entró a una lección y si la completó."""
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='accesos_leccion')
    leccion = models.ForeignKey(Leccion, on_delete=models.CASCADE, related_name='accesos')
    ingreso_en = models.DateTimeField(auto_now_add=True)
    ultima_en = models.DateTimeField(auto_now=True)
    completado = models.BooleanField(default=False)
    completado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ['usuario', 'leccion']
        ordering = ['-ultima_en']
        verbose_name = 'Acceso a lección'
        verbose_name_plural = 'Accesos a lecciones'

    def __str__(self):
        return f'{self.usuario.username} → {self.leccion.titulo}'