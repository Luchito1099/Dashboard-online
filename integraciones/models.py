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
    PROVEEDOR_SHALOM = 'shalom'
    PROVEEDOR_MANUAL = 'manual'
    PROVEEDOR_OTRO = 'otro'
    PROVEEDOR_CHOICES = [
        (PROVEEDOR_SHOPIFY, 'Shopify'),
        (PROVEEDOR_WOOCOMMERCE, 'WooCommerce'),
        (PROVEEDOR_WORDPRESS, 'WordPress'),
        (PROVEEDOR_SHALOM, 'Shalom'),
        (PROVEEDOR_MANUAL, 'Registro manual'),
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

    @classmethod
    def get_manual(cls):
        """Fuente especial (singleton lógico) a la que cuelgan los pedidos dados de
        alta manualmente en el módulo "Registro Pedidos". Así entran al mismo pipeline
        sin romper el código que asume que todo Pedido tiene una Integración."""
        integ, _ = cls.objects.get_or_create(
            proveedor=cls.PROVEEDOR_MANUAL,
            defaults={
                'nombre': 'Registro manual',
                'categoria': cls.CATEGORIA_FUENTE,
                'proposito': cls.PROPOSITO_EXTRACCION,
                'activo': True,
            },
        )
        return integ


class Pedido(models.Model):
    """Pedido extraído de una integración (ej. Shopify). Guarda los campos clave
    para mostrar/operar y el JSON completo en 'datos' por si se necesita más."""

    # ── Estado del flujo de trabajo (propio, no es el estado de Shopify) ──
    # No es una bandera: el pedido avanza por estos estados. 'creado' es la base.
    ESTADO_CREADO = 'creado'
    ESTADO_CONFIRMADO = 'confirmado'
    ESTADO_DESPACHADO = 'despachado'
    ESTADO_ENTREGADO = 'entregado'
    ESTADO_SIN_RESPUESTA = 'sin_respuesta'
    ESTADO_SIN_CONFIRMAR = 'sin_confirmar'
    ESTADO_CANCELADO = 'cancelado'
    ESTADO_CHOICES = [
        (ESTADO_CREADO, 'Pedido creado'),
        (ESTADO_CONFIRMADO, 'Pedido confirmado'),
        (ESTADO_DESPACHADO, 'Despachado / En camino'),
        (ESTADO_ENTREGADO, 'Entregado'),
        (ESTADO_SIN_RESPUESTA, 'Sin respuesta'),
        (ESTADO_SIN_CONFIRMAR, 'No concretó'),
        (ESTADO_CANCELADO, 'Cancelado'),
    ]

    # ── Origen del pedido: automático (sync de una fuente) o manual (alta a mano) ──
    ORIGEN_AUTO = 'auto'
    ORIGEN_MANUAL = 'manual'
    ORIGEN_CHOICES = [
        (ORIGEN_AUTO, 'Automático'),
        (ORIGEN_MANUAL, 'Manual'),
    ]
    # Sub-fuente para pedidos manuales (canal por el que llegó)
    FUENTE_MANUAL_ORGANICO = 'organico'
    FUENTE_MANUAL_PUBLICIDAD = 'publicidad'
    FUENTE_MANUAL_OTRO = 'otro'
    FUENTE_MANUAL_CHOICES = [
        (FUENTE_MANUAL_ORGANICO, 'Orgánico'),
        (FUENTE_MANUAL_PUBLICIDAD, 'Publicidad - Mensajes'),
        (FUENTE_MANUAL_OTRO, 'Otro'),
    ]

    integracion = models.ForeignKey(Integracion, on_delete=models.CASCADE, related_name='pedidos')
    external_id = models.CharField(max_length=64)       # id del pedido en el origen
    numero = models.CharField(max_length=40, blank=True)  # ej. "#1001"

    # Origen y registro manual
    origen = models.CharField(max_length=10, choices=ORIGEN_CHOICES, default=ORIGEN_AUTO)
    fuente_manual = models.CharField(max_length=40, choices=FUENTE_MANUAL_CHOICES, blank=True)
    fuente_manual_detalle = models.CharField(max_length=120, blank=True)  # texto libre si "Otro"
    registrado_por = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='pedidos_registrados')
    # Vendedor al que se le atribuye el pedido (para metas y reportes por vendedor)
    vendedor = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='pedidos_vendedor')

    # Estado del flujo + montos/edición que se operan a mano desde el módulo Pedidos
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default=ESTADO_CREADO)
    adelanto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    editado_por = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='pedidos_editados')
    editado_en = models.DateTimeField(null=True, blank=True)

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
    costo_envio = models.DecimalField(max_digits=12, decimal_places=2, default=0)   # cobrado al cliente
    # Costos reales del negocio (se cargan al cruzar por Excel del courier/fulfillment)
    costo_delivery = models.DecimalField(max_digits=12, decimal_places=2, default=0)      # lo que cobra el courier
    costo_fulfillment = models.DecimalField(max_digits=12, decimal_places=2, default=0)   # lo que cobra el fulfillment
    moneda = models.CharField(max_length=10, blank=True)
    metodo_pago = models.CharField(max_length=120, blank=True)
    estado_pago = models.CharField(max_length=40, blank=True)       # financial_status
    estado_envio = models.CharField(max_length=40, blank=True)      # fulfillment_status

    # Envío / express
    tipo_envio = models.CharField(max_length=120, blank=True)
    es_express = models.BooleanField(default=False)
    # Clave de entrega: código que el cliente da para que le entreguen el producto
    clave = models.CharField(max_length=40, blank=True)

    # Extras
    tags = models.CharField(max_length=255, blank=True)
    nota = models.TextField(blank=True)
    order_status_url = models.URLField(max_length=500, blank=True)

    # Atribución publicitaria (extraída del payload del pedido cuando existe; fuente
    # primaria para cruzar con anuncios de Meta. El match por producto es el respaldo).
    utm_source = models.CharField(max_length=120, blank=True)
    utm_campaign = models.CharField(max_length=200, blank=True)
    utm_content = models.CharField(max_length=200, blank=True)
    ad_id_origen = models.CharField(max_length=64, blank=True)   # id del anuncio de Meta si viene en el tracking

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

    @property
    def restante(self):
        """Lo que falta cobrar: precio final menos el adelanto (nunca negativo)."""
        return max(self.total - self.adelanto, 0)

    def get_seguimiento(self):
        """Devuelve (creando si hace falta) el registro de Seguimiento de este pedido."""
        seg, _ = PedidoSeguimiento.objects.get_or_create(pedido=self)
        return seg


class PedidoItem(models.Model):
    """Producto dentro de un pedido (un pedido puede tener varios)."""
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='items')
    # Producto canónico del catálogo (se resuelve por alias en la sincronización; puede
    # quedar sin vincular si el nombre externo no se reconoce todavía).
    producto = models.ForeignKey('productos.Producto', on_delete=models.SET_NULL,
                                 null=True, blank=True, related_name='lineas_pedido')
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


class PedidoSeguimiento(models.Model):
    """Datos de gestión/seguimiento de un pedido (1:1 con Pedido): contacto, etapa
    del embudo, tipo de cliente, estrategia de venta y notas del vendedor/analista."""

    # Estado de la llamada al cliente
    LLAMADA_NO_CONTACTADO = 'no_contactado'
    LLAMADA_SIN_RESPUESTA = 'sin_respuesta'
    LLAMADA_CONTACTADO = 'contactado'
    LLAMADA_CONTACTADO_SIN_LLAMADA = 'contactado_sin_llamada'
    LLAMADA_CHOICES = [
        (LLAMADA_NO_CONTACTADO, 'No contactado'),
        (LLAMADA_SIN_RESPUESTA, 'Llamado - sin respuesta'),
        (LLAMADA_CONTACTADO, 'Llamado - contactado'),
        (LLAMADA_CONTACTADO_SIN_LLAMADA, 'Contactado sin llamada'),
    ]

    # Tipo de cliente
    TIPO_CLIENTE_CHOICES = [
        ('nuevo', 'Nuevo'),
        ('recurrente', 'Recurrente'),
        ('vip', 'VIP'),
        ('recuperado', 'Recuperado'),
    ]

    # (La "etapa del embudo" se eliminó: el embudo y las visuales se basan en Pedido.estado)

    pedido = models.OneToOneField(Pedido, on_delete=models.CASCADE, related_name='seguimiento')
    llamada_estado = models.CharField(max_length=30, choices=LLAMADA_CHOICES, default=LLAMADA_NO_CONTACTADO)
    llamadas_intentadas = models.PositiveSmallIntegerField(default=0)
    comentario = models.TextField(blank=True)
    tipo_cliente = models.CharField(max_length=20, choices=TIPO_CLIENTE_CHOICES, blank=True)
    estrategia = models.ForeignKey('capacitacion.Estrategia', on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='pedidos')
    actualizado_por = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True,
                                        related_name='seguimientos_actualizados')
    actualizado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Seguimiento de pedido'
        verbose_name_plural = 'Seguimientos de pedidos'

    def __str__(self):
        return f'Seguimiento · {self.pedido}'


class PedidoEditLog(models.Model):
    """Registro cronológico de cada cambio en un pedido (cualquier campo editable,
    de Listado o Seguimiento). Permite ver el historial y revertir (solo admin)."""
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='historial')
    usuario = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='ediciones_pedido')
    campo_modificado = models.CharField(max_length=60)   # 'estado', 'adelanto', 'clave', ...
    valor_anterior = models.CharField(max_length=300, blank=True)
    valor_nuevo = models.CharField(max_length=300, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Cambio de pedido'
        verbose_name_plural = 'Historial de pedidos'

    def __str__(self):
        return f'{self.pedido} · {self.campo_modificado}: {self.valor_anterior} → {self.valor_nuevo}'


def registrar_cambio(pedido, usuario, campo, anterior, nuevo):
    """Crea un PedidoEditLog si el valor cambió. Centraliza el logueo para todas las
    ediciones (Listado, Seguimiento, Registro). Normaliza los valores a str."""
    ant = '' if anterior is None else str(anterior)
    nue = '' if nuevo is None else str(nuevo)
    if ant == nue:
        return None
    return PedidoEditLog.objects.create(
        pedido=pedido,
        usuario=usuario if (usuario and usuario.is_authenticated) else None,
        campo_modificado=campo,
        valor_anterior=ant[:300],
        valor_nuevo=nue[:300],
    )


class FilaPendiente(models.Model):
    """Fila de un Excel de cruce que NO se aplicó (sin cruce o dudosa). Se guarda para
    reconciliarla después contra los pedidos actuales (p. ej. tras registrar la fuente
    manual). El usuario decide re-cruzar o borrar."""
    MOTIVO_SIN_CRUCE = 'sin_cruce'
    MOTIVO_DUDOSO = 'dudoso'
    MOTIVO_CHOICES = [(MOTIVO_SIN_CRUCE, 'Sin cruce'), (MOTIVO_DUDOSO, 'Dudoso')]

    nombre = models.CharField(max_length=200, blank=True)
    celular = models.CharField(max_length=60, blank=True)
    producto = models.CharField(max_length=300, blank=True)
    precio = models.CharField(max_length=40, blank=True)
    costo_delivery = models.CharField(max_length=40, blank=True)
    destino = models.CharField(max_length=300, blank=True)       # destino/dirección tal como vino en el Excel
    estado_texto = models.CharField(max_length=80, blank=True)   # estado tal como vino en el Excel
    motivo = models.CharField(max_length=12, choices=MOTIVO_CHOICES, default=MOTIVO_SIN_CRUCE)
    origen = models.CharField(max_length=120, blank=True)        # etiqueta libre (Excel/empresa)
    creado = models.DateTimeField(auto_now_add=True)
    creado_por = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-creado']
        verbose_name = 'Fila pendiente de cruce'
        verbose_name_plural = 'Filas pendientes de cruce'

    def __str__(self):
        return f'{self.nombre or self.celular} · {self.estado_texto} ({self.motivo})'


# ───────────────────────── Shalom (rastreo por scraper) ─────────────────────────

# Selectores/URLs por defecto (derivados de los scripts del usuario). Editables desde la UI.
DEFAULT_SHALOM_SCRAPER = {
    # Calentamiento de navegación (anti-bot): Google → home Shalom → login
    'google_url': 'https://www.google.com/',
    'home_url': 'https://www.shalom.com.pe/',
    # Etapa 1 — listado (pro.shalom.pe)
    'login_url': 'https://pro.shalom.pe/login?origin=WEB',
    'login_email_sel': '#formLogin input[name="email"]',
    'login_pass_sel': '#passwordLogin',
    'login_remember_sel': '#remember',
    'login_submit_sel': '#formLogin button[type="submit"]',
    'menu_operaciones_sel': '#navbarDropdown-operaciones',
    'menu_seguimiento_text': 'Seguimiento de envíos',
    'row_sel': '.shipment-row',
    'row_status_sel': '.col-status',
    'row_orden_sel': '.order-number',
    'row_codigo_sel': '.code-value',
    'row_contenido_sel': '.content-info div',
    'row_recipient_sel': '.recipient-info div',
    'row_monto_sel': '.amount-info',
    'row_delivery_sel': '.delivery-info div',
    'next_btn_sel': 'button[aria-label="Next"]',
    # Etapa 2 — validación (shalom.com.pe/rastrea)
    'rastrea_url': 'https://shalom.com.pe/rastrea/login',
    'rastrea_email_sel': 'input[type="email"]',
    'rastrea_pass_sel': 'input[type="password"]',
    'rastrea_submit_sel': 'button[type="submit"]',
    'rastrea_orden_sel': 'input[maxlength="8"]',
    'rastrea_codigo_sel': 'input[maxlength="4"]',
    # URL directa del detalle (método principal). {orden}/{codigo} se reemplazan.
    'rastrea_detalle_url': 'https://shalom.com.pe/rastrea/{orden}/{codigo}',
    'rastrea_estado_sel': '.text-4xl.text-red-color-sidebar',
    'rastrea_estado_sel_fallback': '.text-red-color-sidebar',
    # Palabra que indica entrega en el estado real
    'palabra_entregado': 'entregado',
}


class ConfigShalom(models.Model):
    """Ajustes del proveedor Shalom de una integración (OneToOne).
    Las credenciales viven en la Integracion: api_key = usuario, token = contraseña."""
    integracion = models.OneToOneField(Integracion, on_delete=models.CASCADE, related_name='shalom')

    # Horario de actualización
    intervalo_horas = models.PositiveSmallIntegerField(default=6)
    horarios = models.JSONField(default=list, blank=True)   # ["08:00","14:00"] (opcional)
    dias_atras = models.PositiveSmallIntegerField(default=30)
    max_paginas = models.PositiveSmallIntegerField(default=20)

    # Selectores / URLs editables
    config_scraper = models.JSONField(default=dict, blank=True)

    # Configuración avanzada (código completo, opcional). Cifrado.
    codigo_listado = EncryptedTextField(blank=True, default='')
    codigo_validacion = EncryptedTextField(blank=True, default='')
    usar_codigo_avanzado = models.BooleanField(default=False)

    # Marca de agua de corte (de aquí hacia atrás, todo entregado)
    corte_orden = models.CharField(max_length=40, blank=True)
    corte_codigo = models.CharField(max_length=40, blank=True)
    corte_fecha = models.DateField(null=True, blank=True)

    # Estado de ejecución
    corriendo = models.BooleanField(default=False)
    cancelar = models.BooleanField(default=False)   # bandera para detener una corrida
    progreso = models.CharField(max_length=255, blank=True)   # texto de avance en vivo
    latido = models.DateTimeField(null=True, blank=True)  # heartbeat: última señal de vida de la corrida
    ultima_corrida = models.DateTimeField(null=True, blank=True)
    ultimo_resultado = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Configuración Shalom'
        verbose_name_plural = 'Configuración Shalom'

    def __str__(self):
        return f'Shalom · {self.integracion.nombre}'

    def selectores(self):
        """config_scraper con los valores por defecto rellenados."""
        base = dict(DEFAULT_SHALOM_SCRAPER)
        base.update(self.config_scraper or {})
        return base


class EnvioShalom(models.Model):
    """Un envío rastreado en Shalom."""
    integracion = models.ForeignKey(Integracion, on_delete=models.CASCADE, related_name='envios')
    orden = models.CharField(max_length=40)
    codigo = models.CharField(max_length=40)
    estado = models.CharField(max_length=120, blank=True)        # del listado (etapa 1)
    estado_real = models.CharField(max_length=120, blank=True)   # validado (etapa 2)
    entregado = models.BooleanField(default=False)

    producto = models.CharField(max_length=300, blank=True)
    nombre = models.CharField(max_length=200, blank=True)
    dni = models.CharField(max_length=40, blank=True)
    monto = models.CharField(max_length=40, blank=True)
    lugar_entrega = models.CharField(max_length=200, blank=True)
    tipo_envio = models.CharField(max_length=120, blank=True)
    fecha_texto = models.CharField(max_length=60, blank=True)
    fecha_pedido = models.DateField(null=True, blank=True)

    notificado = models.BooleanField(default=False)
    en_alerta = models.BooleanField(default=False)
    primera_vez = models.DateTimeField(auto_now_add=True)
    ultima_validacion = models.DateTimeField(null=True, blank=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-fecha_pedido', '-primera_vez']
        unique_together = ('integracion', 'orden', 'codigo')
        verbose_name = 'Envío Shalom'
        verbose_name_plural = 'Envíos Shalom'

    def __str__(self):
        return f'{self.orden}/{self.codigo} · {self.nombre}'

    def to_dict(self):
        return {
            'id': self.id, 'orden': self.orden, 'codigo': self.codigo,
            'estado': self.estado, 'estado_real': self.estado_real, 'entregado': self.entregado,
            'producto': self.producto, 'nombre': self.nombre, 'dni': self.dni,
            'monto': self.monto, 'lugar_entrega': self.lugar_entrega, 'tipo_envio': self.tipo_envio,
            'fecha': self.fecha_texto, 'en_alerta': self.en_alerta, 'notificado': self.notificado,
            'ultima_validacion': self.ultima_validacion.strftime('%d/%m/%Y %H:%M') if self.ultima_validacion else '',
        }


class CorridaShalom(models.Model):
    """Log de cada corrida del scraper."""
    integracion = models.ForeignKey(Integracion, on_delete=models.CASCADE, related_name='corridas')
    tipo = models.CharField(max_length=10, default='manual')   # auto | manual
    por = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True)
    inicio = models.DateTimeField(auto_now_add=True)
    fin = models.DateTimeField(null=True, blank=True)
    ok = models.BooleanField(null=True, blank=True)
    nuevos = models.PositiveIntegerField(default=0)
    validados = models.PositiveIntegerField(default=0)
    entregados = models.PositiveIntegerField(default=0)
    mensaje = models.TextField(blank=True)

    class Meta:
        ordering = ['-inicio']

    def __str__(self):
        return f'Corrida {self.inicio:%d/%m %H:%M} · {self.integracion.nombre}'
