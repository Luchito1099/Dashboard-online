# integraciones/models.py
from django.db import models

from .crypto import EncryptedTextField


class Integracion(models.Model):
    """Conexión a un servicio externo (Shopify, WooCommerce, courier, etc.).

    Se pueden registrar VARIAS del mismo proveedor (ej. 3 tiendas Shopify). Las
    credenciales sensibles (token, api_key, api_secret) se guardan cifradas en BD.

    Por ahora todas son de propósito 'extraccion' (leen datos). El campo queda
    preparado para futuras integraciones 'actuadora' (que crean pedidos, etc.)."""

    # ── Categoría: separa de dónde vienen los pedidos vs quién los entrega ──
    CATEGORIA_FUENTE = 'fuente_pedidos'
    CATEGORIA_LOGISTICA = 'logistica'
    CATEGORIA_CHOICES = [
        (CATEGORIA_FUENTE, 'Fuente de pedidos'),
        (CATEGORIA_LOGISTICA, 'Empresa de logística'),
    ]

    # ── Proveedor / tipo de servicio ──
    PROVEEDOR_SHOPIFY = 'shopify'
    PROVEEDOR_WOOCOMMERCE = 'woocommerce'
    PROVEEDOR_WORDPRESS = 'wordpress'
    PROVEEDOR_OTRO = 'otro'
    PROVEEDOR_CHOICES = [
        (PROVEEDOR_SHOPIFY, 'Shopify'),
        (PROVEEDOR_WOOCOMMERCE, 'WooCommerce'),
        (PROVEEDOR_WORDPRESS, 'WordPress'),
        (PROVEEDOR_OTRO, 'Otro'),
    ]

    # ── Propósito: extracción ahora; actuadora reservado para el futuro ──
    PROPOSITO_EXTRACCION = 'extraccion'
    PROPOSITO_ACTUADORA = 'actuadora'
    PROPOSITO_CHOICES = [
        (PROPOSITO_EXTRACCION, 'Extracción (leer datos)'),
        (PROPOSITO_ACTUADORA, 'Actuadora (crear/modificar)'),
    ]

    nombre = models.CharField(max_length=120, help_text='Alias, ej. "Tienda principal PE"')
    etiqueta = models.CharField(max_length=80, blank=True, help_text='Clasificación libre')
    categoria = models.CharField(max_length=20, choices=CATEGORIA_CHOICES, default=CATEGORIA_FUENTE)
    proveedor = models.CharField(max_length=20, choices=PROVEEDOR_CHOICES, default=PROVEEDOR_SHOPIFY)
    proposito = models.CharField(max_length=20, choices=PROPOSITO_CHOICES, default=PROPOSITO_EXTRACCION)

    # Conexión: dominio Shopify "xxx.myshopify.com" o URL del sitio
    tienda_url = models.CharField(max_length=255, blank=True)
    api_version = models.CharField(max_length=20, blank=True, default='2024-10',
                                   help_text='Versión de la API (Shopify)')

    # Credenciales (cifradas en BD; las vistas las manejan en texto plano)
    token = EncryptedTextField(blank=True, default='', help_text='Admin API access token (Shopify)')
    api_key = EncryptedTextField(blank=True, default='', help_text='Consumer key (WooCommerce)')
    api_secret = EncryptedTextField(blank=True, default='', help_text='Consumer secret (WooCommerce)')

    activo = models.BooleanField(default=True)
    orden = models.PositiveSmallIntegerField(default=0)

    # Resultado del último "Probar conexión"
    ultimo_test_ok = models.BooleanField(null=True, blank=True)
    ultimo_test_msg = models.CharField(max_length=255, blank=True)
    ultimo_test_en = models.DateTimeField(null=True, blank=True)

    creado = models.DateTimeField(auto_now_add=True)       # fecha de conexión
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['categoria', 'orden', 'nombre']
        verbose_name = 'Integración'
        verbose_name_plural = 'Integraciones'

    def __str__(self):
        return f'{self.nombre} ({self.get_proveedor_display()})'

    @staticmethod
    def _enmascarar(secreto):
        """Muestra solo los últimos 4 caracteres: 'shpat_••••1234'. '' si está vacío."""
        if not secreto:
            return ''
        if len(secreto) <= 4:
            return '••••'
        return f'••••{secreto[-4:]}'

    @property
    def token_enmascarado(self):
        return self._enmascarar(self.token)

    @property
    def api_key_enmascarado(self):
        return self._enmascarar(self.api_key)

    @property
    def api_secret_enmascarado(self):
        return self._enmascarar(self.api_secret)
