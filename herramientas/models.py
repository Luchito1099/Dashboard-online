# herramientas/models.py
from django.db import models


class HerramientaExterna(models.Model):
    """Enlace a una herramienta externa aún no integrada (n8n, Chatwoot, Shopify, etc.)."""
    nombre = models.CharField(max_length=120)
    descripcion = models.CharField(max_length=200, blank=True)
    url = models.URLField()
    icono = models.CharField(max_length=10, blank=True)      # emoji
    categoria = models.CharField(max_length=80, blank=True)
    activo = models.BooleanField(default=True)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['orden', 'nombre']
        verbose_name = 'Herramienta externa'
        verbose_name_plural = 'Herramientas externas'

    def __str__(self):
        return self.nombre
