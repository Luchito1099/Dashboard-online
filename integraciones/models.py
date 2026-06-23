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
    token = EncryptedTextField(blank=True, default='', help_text='Access token obtenido por OAuth o Custom App (Shopify)')
    api_key = EncryptedTextField(blank=True, default='', help_text='Client ID (Shopify OAuth) / Consumer key (WooCommerce)')
    api_secret = EncryptedTextField(blank=True, default='', help_text='Client Secret (Shopify OAuth) / Consumer secret (WooCommerce)')

    # Permisos solicitados en el OAuth de Shopify.
    # read_all_orders es necesario para acceder a pedidos de más de 60 días (historial completo).
    scopes = models.CharField(max_length=255, blank=True, default='read_orders,read_all_orders')

    activo = models.BooleanField(default=True)
    orden = models.PositiveSmallIntegerField(default=0)

    # Resultado del último "Probar conexión"
    ultimo_test_ok = models.BooleanField(null=True, blank=True)
    ultimo_test_msg = models.CharField(max_length=255, blank=True)
    ultimo_test_en = models.DateTimeField(null=True, blank=True)

    # Resultado de la última sincronización de pedidos
    ultimo_sync_ok = models.BooleanField(null=True, blank=True)
    ultimo_sync_msg = models.CharField(max_length=255, blank=True)
    ultimo_sync_en = models.DateTimeField(null=True, blank=True)

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

    @property
    def pedidos_count(self):
        return self.pedidos.count()


class Pedido(models.Model):
    """Pedido extraído de una integración (ej. Shopify). Guarda los campos clave
    para mostrar/operar y el JSON completo en 'datos' por si se necesita más."""
    integracion = models.ForeignKey(Integracion, on_delete=models.CASCADE, related_name='pedidos')
    external_id = models.CharField(max_length=64)       # id del pedido en el origen
    numero = models.CharField(max_length=40, blank=True)  # ej. "#1001"

    # Cliente y entrega
    nombre_cliente = models.CharField(max_length=200, blank=True)
    telefono = models.CharField(max_length=40, blank=True)
    email = models.CharField(max_length=200, blank=True)
    direccion = models.CharField(max_length=300, blank=True)
    distrito = models.CharField(max_length=120, blank=True)
    provincia = models.CharField(max_length=120, blank=True)
    pais = models.CharField(max_length=80, blank=True)
    latitud = models.FloatField(null=True, blank=True)
    longitud = models.FloatField(null=True, blank=True)

    # Pago y montos
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    descuentos = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    costo_envio = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    moneda = models.CharField(max_length=10, blank=True)
    metodo_pago = models.CharField(max_length=120, blank=True)
    estado_pago = models.CharField(max_length=40, blank=True)       # financial_status
    estado_envio = models.CharField(max_length=40, blank=True)      # fulfillment_status

    # Envío / express
    tipo_envio = models.CharField(max_length=120, blank=True)
    es_express = models.BooleanField(default=False)

    # Extras
    tags = models.CharField(max_length=255, blank=True)
    nota = models.TextField(blank=True)
    order_status_url = models.URLField(max_length=500, blank=True)

    fecha_pedido = models.DateTimeField(null=True, blank=True)
    datos = models.JSONField(default=dict, blank=True)   # payload completo del origen
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-fecha_pedido']
        unique_together = ('integracion', 'external_id')
        verbose_name = 'Pedido'
        verbose_name_plural = 'Pedidos'

    def __str__(self):
        return f'{self.numero or self.external_id} · {self.integracion.nombre}'

    @property
    def ubicacion(self):
        """Resumen 'Distrito, Provincia' para mostrar en tablas."""
        return ', '.join(filter(None, [self.distrito, self.provincia]))


class PedidoItem(models.Model):
    """Producto dentro de un pedido (un pedido puede tener varios)."""
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='items')
    nombre = models.CharField(max_length=255)
    variante = models.CharField(max_length=120, blank=True)
    sku = models.CharField(max_length=120, blank=True)
    cantidad = models.PositiveIntegerField(default=1)
    precio = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    vendor = models.CharField(max_length=120, blank=True)
    product_id = models.CharField(max_length=64, blank=True)
    variant_id = models.CharField(max_length=64, blank=True)

    def __str__(self):
        return f'{self.cantidad}× {self.nombre}'
