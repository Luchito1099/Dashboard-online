from django.db import models
from django.contrib.auth.models import User


class Perfil(models.Model):
    ROL_CHOICES = [
        ('admin', 'Administrador'),
        ('analista', 'Analista'),
        ('marketing', 'Analista de Marketing'),
        ('vendedor', 'Vendedor'),
    ]

    usuario = models.OneToOneField(User, on_delete=models.CASCADE)
    rol = models.CharField(max_length=10, choices=ROL_CHOICES, default='vendedor')
    activo = models.BooleanField(default=True)
    # Filtro fijado del módulo Pedidos (querystring), atado al usuario y portable entre dispositivos
    pedidos_filtro = models.TextField(blank=True, default='')
    # Filtro fijado del dashboard de Publicidad (mismo mecanismo)
    ads_filtro = models.TextField(blank=True, default='')

    class Meta:
        verbose_name = 'Perfil'
        verbose_name_plural = 'Perfiles'

    def __str__(self):
        return f"{self.usuario.username} · {self.rol}"

    def es_admin(self):
        return self.rol == 'admin'

    def es_analista(self):
        return self.rol == 'analista'

    def es_marketing(self):
        return self.rol == 'marketing'

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
    # Seguimiento, Registro y Avances de Pedidos (rol vendedor)
    vendedor_puede_ver_seguimiento = models.BooleanField(default=False)
    vendedor_puede_editar_seguimiento = models.BooleanField(default=False)
    vendedor_puede_registrar_pedidos = models.BooleanField(default=False)
    vendedor_puede_ver_avances = models.BooleanField(default=False)
    # Edición limitada del analista (puede operar Seguimiento aunque sea rol de lectura)
    analista_puede_editar_seguimiento = models.BooleanField(default=True)

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


class MetaVendedor(models.Model):
    """Meta diaria de un vendedor: cantidad de pedidos y/o monto de venta esperados por día.
    Sirve para que cada vendedor se mida contra su objetivo en la vista Avances."""
    usuario = models.OneToOneField(User, on_delete=models.CASCADE, related_name='meta')
    pedidos_dia = models.PositiveSmallIntegerField(default=0)
    monto_dia = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        verbose_name = 'Meta de vendedor'
        verbose_name_plural = 'Metas de vendedores'

    def __str__(self):
        return f'Meta de {self.usuario.username}: {self.pedidos_dia}/día'