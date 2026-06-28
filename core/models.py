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


class ConexionIA(models.Model):
    """Una conexión a un proveedor de IA (Claude, OpenAI, DeepSeek, OpenRouter o
    personalizada). Se pueden tener varias y elegir cuál usa cada tarea. La API key se
    guarda cifrada. Lleva contadores de consumo (tokens/llamadas) para saber el gasto."""
    from integraciones.crypto import EncryptedTextField

    PROVEEDOR_ANTHROPIC = 'anthropic'
    PROVEEDOR_OPENAI = 'openai'
    PROVEEDOR_DEEPSEEK = 'deepseek'
    PROVEEDOR_OPENROUTER = 'openrouter'
    PROVEEDOR_CUSTOM = 'custom'
    PROVEEDOR_CHOICES = [
        (PROVEEDOR_ANTHROPIC, 'Anthropic (Claude)'),
        (PROVEEDOR_OPENAI, 'OpenAI'),
        (PROVEEDOR_DEEPSEEK, 'DeepSeek'),
        (PROVEEDOR_OPENROUTER, 'OpenRouter'),
        (PROVEEDOR_CUSTOM, 'Personalizada (compatible OpenAI)'),
    ]

    nombre = models.CharField(max_length=80, help_text='Etiqueta para identificarla, ej. "Claude principal"')
    proveedor = models.CharField(max_length=20, choices=PROVEEDOR_CHOICES, default=PROVEEDOR_ANTHROPIC)
    modelo = models.CharField(max_length=100, default='claude-haiku-4-5-20251001')
    base_url = models.CharField(max_length=200, blank=True, default='',
                                help_text='Solo para proveedores compatibles con OpenAI o personalizada.')
    api_key = EncryptedTextField(blank=True, default='')
    activa = models.BooleanField(default=True)

    # Consumo acumulado (se incrementa cuando una tarea usa esta conexión)
    tokens_entrada = models.BigIntegerField(default=0)
    tokens_salida = models.BigIntegerField(default=0)
    llamadas = models.PositiveIntegerField(default=0)

    # Resultado de la última "Probar conexión"
    ultimo_test_ok = models.BooleanField(null=True, blank=True)
    ultimo_test_msg = models.CharField(max_length=255, blank=True)
    ultimo_test_en = models.DateTimeField(null=True, blank=True)

    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nombre']
        verbose_name = 'Conexión de IA'
        verbose_name_plural = 'Conexiones de IA'

    def __str__(self):
        return f'{self.nombre} ({self.get_proveedor_display()})'

    @property
    def key_enmascarada(self):
        t = self.api_key
        if not t:
            return ''
        return f'••••{t[-4:]}' if len(t) > 4 else '••••'

    @property
    def tokens_total(self):
        return self.tokens_entrada + self.tokens_salida


PROMPT_REGISTRAR_PEDIDO = (
    'Eres un asistente que extrae los datos de un pedido a partir de una conversación '
    '(WhatsApp, Instagram, etc.). Responde SOLO con un JSON, sin texto adicional ni '
    'backticks, con esta forma exacta:\n'
    '{"nombre_cliente":"","telefono":"","numero":"","fecha":"","productos":[{"nombre":"","cantidad":1,'
    '"precio":""}],"total":"","adelanto":"","tipo_envio":"","tipo_envio_detalle":""}\n'
    '- "fecha" es la fecha del pedido en formato YYYY-MM-DD si aparece en el texto (si no, "").\n'
    '- "tipo_envio" debe ser uno de: "Agencia", "Delivery" u "Otros". Si es otro, deja '
    'tipo_envio en "Otros" y pon el detalle en "tipo_envio_detalle".\n'
    '- Los montos (total, adelanto, precio) solo con números, sin símbolo de moneda.\n'
    '- "productos" es la lista de artículos pedidos (nombre, cantidad, precio si aparece).\n'
    '- Si un dato no aparece en la conversación, déjalo como "" (cadena vacía) y NO lo '
    'inventes. No agregues campos que no estén en el JSON.'
)


PROMPT_MATCHING_PEDIDOS = (
    'Eres un asistente que decide a qué pedido del sistema corresponde una fila de un '
    'Excel de entregas. Te doy una fila (nombre, celular, producto) y una lista de '
    'pedidos candidatos con su id. Responde SOLO con un JSON, sin texto ni backticks:\n'
    '{"pedido_id": null}\n'
    '- Pon en "pedido_id" el id del pedido que corresponde a la fila, o null si ninguno '
    'coincide con seguridad.\n'
    '- Prioriza el celular; si no hay celular, usa nombre y producto.\n'
    '- No inventes ids: usa solo los de la lista de candidatos.'
)


class HerramientaIA(models.Model):
    """Una tarea donde se puede usar IA (con su propio prompt y la conexión que usa).
    Es extensible; cableadas: 'registrar_pedido' y 'matching_pedidos'."""
    slug = models.SlugField(max_length=50, unique=True)
    nombre = models.CharField(max_length=80)
    descripcion = models.CharField(max_length=255, blank=True)
    prompt = models.TextField(blank=True)
    conexion = models.ForeignKey(ConexionIA, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='herramientas')
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ['nombre']
        verbose_name = 'Herramienta con IA'
        verbose_name_plural = 'Herramientas con IA'

    def __str__(self):
        return self.nombre

    @property
    def lista_para_usar(self):
        """True si está activa y tiene una conexión activa con API key."""
        return bool(self.activa and self.conexion and self.conexion.activa and self.conexion.api_key)

    @classmethod
    def _seed(cls, slug, nombre, descripcion, prompt):
        obj, creado = cls.objects.get_or_create(
            slug=slug, defaults={'nombre': nombre, 'descripcion': descripcion, 'prompt': prompt})
        if creado and ConexionIA.objects.filter(activa=True).exists():
            obj.conexion = ConexionIA.objects.filter(activa=True).first()
            obj.save(update_fields=['conexion'])
        return obj

    @classmethod
    def registrar_pedido(cls):
        """Devuelve (creando si falta) la herramienta de autocompletar el registro de pedidos."""
        return cls._seed('registrar_pedido', 'Registrar pedido',
                         'Pega una conversación y autocompleta el formulario de pedido manual.',
                         PROMPT_REGISTRAR_PEDIDO)

    @classmethod
    def matching_pedidos(cls):
        """Devuelve (creando si falta) la herramienta de cruce de pedidos por Excel."""
        return cls._seed('matching_pedidos', 'Matching de pedidos (Excel)',
                         'Resuelve los cruces dudosos al subir un Excel para confirmar pedidos.',
                         PROMPT_MATCHING_PEDIDOS)