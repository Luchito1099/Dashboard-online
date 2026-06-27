# anuncios/models.py
"""Módulo de Publicidad (Meta Ads): conecta el gasto en Meta con la realidad del
negocio (pedidos confirmados/entregados). Los datos llegan desde un workflow n8n
vía webhook; el ERP los guarda, los casa con productos y calcula métricas reales."""
from django.db import models

from integraciones.crypto import EncryptedTextField


class CuentaPublicitaria(models.Model):
    """Cuenta publicitaria (ad account) de una plataforma. Guarda el token de la Graph
    API (cifrado) para que el ERP extraiga los datos directamente. Se asocia opcionalmente
    a una Integración/tienda (Dashboard, NovaShop) para atribuir y filtrar por tienda."""
    PLATAFORMA_META = 'meta'
    PLATAFORMA_CHOICES = [
        (PLATAFORMA_META, 'Meta (Facebook/Instagram)'),
    ]

    plataforma = models.CharField(max_length=20, choices=PLATAFORMA_CHOICES, default=PLATAFORMA_META)
    ad_account_id = models.CharField(max_length=64, unique=True,
                                     help_text='Con prefijo act_, ej. act_123456789')
    nombre = models.CharField(max_length=120)
    # Tienda asociada (la fuente de pedidos a la que pertenece esta cuenta)
    integracion = models.ForeignKey('integraciones.Integracion', on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='cuentas_publicitarias')

    # Conexión directa a la Graph API de Meta
    access_token = EncryptedTextField(blank=True, default='',
                                      help_text='Token de System User con permiso ads_read (cifrado en BD)')
    api_version = models.CharField(max_length=10, default='v21.0')

    activo = models.BooleanField(default=True)

    # Resultado de la última "Probar conexión" / "Sincronizar"
    ultimo_test_ok = models.BooleanField(null=True, blank=True)
    ultimo_test_msg = models.CharField(max_length=255, blank=True)
    ultimo_test_en = models.DateTimeField(null=True, blank=True)
    ultimo_sync_ok = models.BooleanField(null=True, blank=True)
    ultimo_sync_msg = models.CharField(max_length=255, blank=True)
    ultimo_sync_en = models.DateTimeField(null=True, blank=True)

    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nombre']
        verbose_name = 'Cuenta publicitaria'
        verbose_name_plural = 'Cuentas publicitarias'

    def __str__(self):
        return f'{self.nombre} ({self.ad_account_id})'

    @property
    def token_enmascarado(self):
        t = self.access_token
        if not t:
            return ''
        return f'••••{t[-4:]}' if len(t) > 4 else '••••'


class CampanaMeta(models.Model):
    """Estructura de un anuncio en Meta (una fila por AD, con sus campaign/adset).
    Se sincroniza desde el webhook de n8n. El admin marca 'incluir_en_extraccion'
    para decidir cuáles entran al pipeline de insights."""
    cuenta = models.ForeignKey(CuentaPublicitaria, on_delete=models.CASCADE, related_name='anuncios')

    campaign_id = models.CharField(max_length=64)
    campaign_name = models.CharField(max_length=255, blank=True)
    adset_id = models.CharField(max_length=64, blank=True)
    adset_name = models.CharField(max_length=255, blank=True)
    ad_id = models.CharField(max_length=64)
    ad_name = models.CharField(max_length=255, blank=True)

    # Se descarga TODO siempre. Este flag es un filtro de ANÁLISIS: si está en True,
    # el anuncio entra a los dashboards/tablas. Por defecto True (todos incluidos).
    incluir_en_extraccion = models.BooleanField(default=True)
    # Etiqueta libre para organizar/agrupar anuncios (ej. "Mensajes", "Producto X", "Test")
    etiqueta = models.CharField(max_length=60, blank=True)
    # Proyecto al que pertenece la campaña (un proyecto = un conjunto de campañas)
    proyecto = models.CharField(max_length=80, blank=True)

    primero_visto = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['campaign_name', 'adset_name', 'ad_name']
        unique_together = ('cuenta', 'ad_id')
        verbose_name = 'Anuncio de Meta'
        verbose_name_plural = 'Anuncios de Meta'

    def __str__(self):
        return self.ad_name or self.adset_name or self.campaign_name or self.ad_id


class InsightDiarioMeta(models.Model):
    """Métricas de gasto de un anuncio en un día (lo que Meta reporta)."""
    campana = models.ForeignKey(CampanaMeta, on_delete=models.CASCADE, related_name='insights')
    fecha = models.DateField()
    gasto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    impresiones = models.PositiveIntegerField(default=0)
    clicks = models.PositiveIntegerField(default=0)
    resultados = models.PositiveIntegerField(default=0)   # leads/compras que Meta atribuye
    moneda = models.CharField(max_length=10, blank=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-fecha']
        unique_together = ('campana', 'fecha')
        verbose_name = 'Insight diario (Meta)'
        verbose_name_plural = 'Insights diarios (Meta)'

    def __str__(self):
        return f'{self.campana} · {self.fecha} · S/ {self.gasto}'


class InsightHorarioMeta(models.Model):
    """Métricas por hora del día (breakdown horario de Meta), para el heatmap."""
    campana = models.ForeignKey(CampanaMeta, on_delete=models.CASCADE, related_name='insights_hora')
    fecha = models.DateField()
    hora = models.PositiveSmallIntegerField()   # 0–23 (zona horaria del anunciante)
    gasto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    impresiones = models.PositiveIntegerField(default=0)
    clicks = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-fecha', 'hora']
        unique_together = ('campana', 'fecha', 'hora')
        verbose_name = 'Insight horario (Meta)'
        verbose_name_plural = 'Insights horarios (Meta)'

    def __str__(self):
        return f'{self.campana} · {self.fecha} {self.hora:02d}h'


class MatchProductoAnuncio(models.Model):
    """Match permanente entre un anuncio (nivel ad) y un producto del catálogo.
    Un anuncio vende un producto. Confirmado a mano queda con confianza=100."""
    ORIGEN_MANUAL = 'manual'
    ORIGEN_SUGERIDO = 'sugerido'
    ORIGEN_CHOICES = [
        (ORIGEN_MANUAL, 'Manual'),
        (ORIGEN_SUGERIDO, 'Sugerido automático'),
    ]

    campana = models.OneToOneField(CampanaMeta, on_delete=models.CASCADE, related_name='match')
    producto = models.ForeignKey('productos.Producto', on_delete=models.CASCADE,
                                 related_name='matches_anuncio')
    origen = models.CharField(max_length=10, choices=ORIGEN_CHOICES, default=ORIGEN_MANUAL)
    confianza = models.PositiveSmallIntegerField(default=100)   # manual=100; sugerido=score 0-100
    creado_por = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='matches_anuncio')
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Match producto-anuncio'
        verbose_name_plural = 'Matches producto-anuncio'

    def __str__(self):
        return f'{self.campana} → {self.producto}'


class UmbralAlerta(models.Model):
    """Configuración de alertas (singleton, pk=1): si el CPA real supera el umbral
    durante N días consecutivos, se notifica vía webhook a n8n (Telegram)."""
    cpa_max = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    dias_consecutivos = models.PositiveSmallIntegerField(default=3)
    n8n_webhook_url = models.URLField(blank=True)
    activo = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Umbral de alerta'
        verbose_name_plural = 'Umbrales de alerta'

    def __str__(self):
        return f'Alerta CPA > {self.cpa_max} ({self.dias_consecutivos} días)'

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class AlertaEnviada(models.Model):
    """Registro de alertas ya enviadas (para no repetir la misma el mismo día)."""
    campana = models.ForeignKey(CampanaMeta, on_delete=models.CASCADE, related_name='alertas')
    fecha = models.DateField()
    cpa = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    enviada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha']
        unique_together = ('campana', 'fecha')
        verbose_name = 'Alerta enviada'
        verbose_name_plural = 'Alertas enviadas'

    def __str__(self):
        return f'{self.campana} · {self.fecha} · CPA {self.cpa}'
