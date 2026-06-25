from django.db import models
from django.contrib.auth.models import User


class Perfil(models.Model):
    ROL_CHOICES = [
        ('admin', 'Administrador'),
        ('vendedor', 'Vendedor'),
    ]

    usuario = models.OneToOneField(User, on_delete=models.CASCADE)
    rol = models.CharField(max_length=10, choices=ROL_CHOICES, default='vendedor')
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Perfil'
        verbose_name_plural = 'Perfiles'

    def __str__(self):
        return f"{self.usuario.username} · {self.rol}"

    def es_admin(self):
        return self.rol == 'admin'

    def es_vendedor(self):
        return self.rol == 'vendedor'


class ConfiguracionSistema(models.Model):
    """Configuración global del sistema (singleton: siempre una sola fila, pk=1).
    Controla qué puede hacer el rol vendedor."""
    vendedor_puede_editar_videos = models.BooleanField(default=True)
    vendedor_puede_ver_productos = models.BooleanField(default=True)
    vendedor_puede_ver_inicio = models.BooleanField(default=True)
    vendedor_puede_ver_capacitacion = models.BooleanField(default=True)
    vendedor_puede_ver_herramientas = models.BooleanField(default=True)
    vendedor_puede_compartir = models.BooleanField(default=True)
    # Módulo Pedidos (datos financieros → desactivado por defecto, el admin lo habilita)
    vendedor_puede_ver_pedidos = models.BooleanField(default=False)
    vendedor_puede_editar_pedidos = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Configuración del sistema'
        verbose_name_plural = 'Configuración del sistema'

    def __str__(self):
        return 'Configuración del sistema'

    @classmethod
    def get_solo(cls):
        """Devuelve la única fila de configuración, creándola con valores por defecto si no existe."""
        config, _ = cls.objects.get_or_create(pk=1)
        return config