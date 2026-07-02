# rotulador/models.py
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

from integraciones.crypto import EncryptedTextField


DEFAULT_PROMPT = (
    'Extrae los datos de envío del siguiente texto y responde SOLO con un JSON sin '
    'texto adicional ni backticks:\n'
    '{"nombres":"nombre completo del destinatario","destino":"dirección completa de '
    'entrega","agencia":"empresa courier o agencia de envío","celular":"número de '
    'celular","dni":"número de DNI o documento","producto":"descripción del producto o '
    'pedido"}\n'
    'Si un campo no aparece en el texto, usa "" (cadena vacía). No inventes datos.'
)

DEFAULT_VISUAL = {
    'headerBg': '#fdfcfa', 'footerBg': '#fdfcfa', 'bodyBg': '#ffffff',
    'nameFontSize': 14, 'accentBarHeight': 4, 'borderRadius': 3,
    'showBarcode': True, 'showCutMarks': True, 'showFragile': True, 'showCounter': True,
}

DEFAULT_PRODUCTS = [
    {'nombre': 'TOBILLERA NOVAFIT', 'mercaderia': 'PAQUETE XS'},
    {'nombre': 'RODILLERA NOVAFIT', 'mercaderia': 'PAQUETE XS'},
    {'nombre': 'MUÑEQUERA NOVAFIT', 'mercaderia': 'PAQUETE XS'},
    {'nombre': 'TELAS REFLECTIVAS NOVASHOP', 'mercaderia': 'PAQUETE S'},
]


class RotuladorConfig(models.Model):
    """Configuración global del rotulador (singleton pk=1): marca, estilo, logos,
    productos y credenciales de IA (cifradas)."""
    brand = models.CharField(max_length=80, default='Dashboard')
    initial = models.CharField(max_length=2, default='K')
    accent = models.CharField(max_length=20, default='#c0532a')
    label_style = models.CharField(max_length=20, default='classic')  # classic|bold|minimal

    visual = models.JSONField(default=dict, blank=True)
    logos = models.JSONField(default=list, blank=True)       # [{id,name,dataUrl}]
    active_logo = models.BigIntegerField(null=True, blank=True)
    productos = models.JSONField(default=list, blank=True)   # [{nombre,mercaderia}]

    # IA (proxy en el servidor; compatible con Anthropic y APIs estilo OpenAI)
    ai_provider = models.CharField(max_length=30, default='anthropic')
    ai_base_url = models.CharField(max_length=200, blank=True, default='')
    ai_model = models.CharField(max_length=80, default='claude-haiku-4-5-20251001')
    ai_api_key = EncryptedTextField(blank=True, default='')
    prompt = models.TextField(blank=True, default=DEFAULT_PROMPT)

    class Meta:
        verbose_name = 'Configuración del rotulador'
        verbose_name_plural = 'Configuración del rotulador'

    def __str__(self):
        return 'Configuración del rotulador'

    @classmethod
    def get_solo(cls):
        config, creado = cls.objects.get_or_create(pk=1)
        if creado:
            config.visual = dict(DEFAULT_VISUAL)
            config.productos = [dict(p) for p in DEFAULT_PRODUCTS]
            config.save()
        return config


class Rotulo(models.Model):
    """Un rótulo de envío en la lista de trabajo (se persiste en BD)."""
    ORIGEN_CHOICES = [
        ('shopify', 'Shopify'),
        ('mensaje', 'Mensaje'),
        ('manual', 'Manual'),
    ]

    nombres = models.CharField(max_length=200, blank=True)
    destino = models.CharField(max_length=400, blank=True)
    agencia = models.CharField(max_length=200, blank=True)
    celular = models.CharField(max_length=40, blank=True)
    dni = models.CharField(max_length=40, blank=True)
    producto = models.CharField(max_length=300, blank=True)
    cantidad = models.PositiveIntegerField(default=1)

    origen = models.CharField(max_length=20, choices=ORIGEN_CHOICES, default='manual')
    pedido = models.ForeignKey(
        'integraciones.Pedido', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='rotulos',
    )
    creado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-creado']
        verbose_name = 'Rótulo'
        verbose_name_plural = 'Rótulos'

    def __str__(self):
        return f'{self.nombres or "(sin nombre)"} · {self.get_origen_display()}'

    def to_dict(self):
        # Se guarda en UTC (USE_TZ) y se muestra/agrupa en hora local (America/Lima),
        # para que el filtro por día del rotulador coincida con la fecha real del negocio.
        creado_local = timezone.localtime(self.creado) if self.creado else None
        actualizado_local = timezone.localtime(self.actualizado) if self.actualizado else None
        return {
            'id': self.id,
            'nombres': self.nombres,
            'destino': self.destino,
            'agencia': self.agencia,
            'celular': self.celular,
            'dni': self.dni,
            'producto': self.producto,
            'cantidad': self.cantidad,
            'origen': self.origen,
            'pedido_id': self.pedido_id,
            'creado_por': (self.creado_por.get_full_name() or self.creado_por.username) if self.creado_por else '',
            'creado': creado_local.strftime('%d/%m/%Y %H:%M') if creado_local else '',
            'creado_iso': creado_local.strftime('%Y-%m-%d') if creado_local else '',
            'actualizado_iso': actualizado_local.strftime('%Y-%m-%d') if actualizado_local else '',
        }
