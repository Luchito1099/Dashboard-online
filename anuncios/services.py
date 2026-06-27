# anuncios/services.py
"""Lógica del módulo Publicidad: verificación del webhook, ingesta del payload de n8n,
atribución pedido↔anuncio y agregaciones para los dashboards (serie diaria, tabla por
producto, heatmap) y la evaluación de alertas."""
import base64
import hashlib
import hmac
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Sum, Count
from django.db.models.functions import TruncDate, ExtractHour
from django.utils import timezone

from .models import (CuentaPublicitaria, CampanaMeta, InsightDiarioMeta,
                     InsightHorarioMeta, MatchProductoAnuncio)

# Estados de Pedido que cuentan como venta concretada (confirmada en adelante)
from integraciones.models import Pedido, PedidoEditLog

ESTADOS_CONFIRMADOS = [Pedido.ESTADO_CONFIRMADO, Pedido.ESTADO_DESPACHADO, Pedido.ESTADO_ENTREGADO]
LABEL_CONFIRMADO = dict(Pedido.ESTADO_CHOICES)[Pedido.ESTADO_CONFIRMADO]   # 'Pedido confirmado'
LABEL_ENTREGADO = dict(Pedido.ESTADO_CHOICES)[Pedido.ESTADO_ENTREGADO]     # 'Entregado'


# ───────────────────────── Webhook n8n ─────────────────────────

def verificar_firma(body_bytes, firma_header):
    """Valida la firma HMAC-SHA256 (base64) que n8n manda en X-Dashboard-Sign, firmada
    con settings.N8N_WEBHOOK_SECRET. Mismo patrón que el webhook de Shopify."""
    secret = settings.N8N_WEBHOOK_SECRET
    if not secret or not firma_header:
        return False
    digest = hmac.new(secret.encode(), body_bytes, hashlib.sha256).digest()
    calculado = base64.b64encode(digest).decode()
    return hmac.compare_digest(calculado, firma_header)


def _dec(v):
    try:
        return Decimal(str(v)) if v not in (None, '') else Decimal('0')
    except Exception:
        return Decimal('0')


def _int(v):
    try:
        return int(v) if v not in (None, '') else 0
    except Exception:
        return 0


def ingerir_payload(data):
    """Procesa el payload (de la Graph API o de n8n). Hace upsert de la cuenta y de cada
    anuncio (estructura) y guarda TODOS sus insights (siempre se baja todo). El filtrado
    de qué anuncios se muestran ocurre después, en el análisis (incluir_en_extraccion).
    Devuelve un resumen de lo procesado."""
    resumen = {'anuncios': 0, 'anuncios_nuevos': 0, 'insights_guardados': 0}

    cuenta_data = data.get('cuenta') or {}
    ad_account_id = (cuenta_data.get('ad_account_id') or '').strip()
    if not ad_account_id:
        return {'error': 'Falta cuenta.ad_account_id'}

    cuenta, _ = CuentaPublicitaria.objects.get_or_create(
        ad_account_id=ad_account_id,
        defaults={'nombre': cuenta_data.get('nombre') or ad_account_id},
    )

    for a in (data.get('anuncios') or []):
        ad_id = str(a.get('ad_id') or '').strip()
        if not ad_id:
            continue
        campana, creado = CampanaMeta.objects.update_or_create(
            cuenta=cuenta, ad_id=ad_id,
            defaults={
                'campaign_id': str(a.get('campaign_id') or ''),
                'campaign_name': a.get('campaign_name') or '',
                'adset_id': str(a.get('adset_id') or ''),
                'adset_name': a.get('adset_name') or '',
                'ad_name': a.get('ad_name') or '',
            },
        )
        resumen['anuncios'] += 1
        if creado:
            resumen['anuncios_nuevos'] += 1

        # Siempre se guardan los insights (se baja todo); el filtro es de análisis.
        for ins in (a.get('insights_diarios') or []):
            if not ins.get('fecha'):
                continue
            InsightDiarioMeta.objects.update_or_create(
                campana=campana, fecha=ins['fecha'],
                defaults={
                    'gasto': _dec(ins.get('gasto')),
                    'impresiones': _int(ins.get('impresiones')),
                    'clicks': _int(ins.get('clicks')),
                    'resultados': _int(ins.get('resultados')),
                    'moneda': ins.get('moneda') or '',
                },
            )
            resumen['insights_guardados'] += 1

        for ins in (a.get('insights_horarios') or []):
            if ins.get('fecha') is None or ins.get('hora') is None:
                continue
            InsightHorarioMeta.objects.update_or_create(
                campana=campana, fecha=ins['fecha'], hora=_int(ins.get('hora')),
                defaults={
                    'gasto': _dec(ins.get('gasto')),
                    'impresiones': _int(ins.get('impresiones')),
                    'clicks': _int(ins.get('clicks')),
                },
            )
            resumen['insights_guardados'] += 1

    return resumen


# ───────────────────────── Agregaciones para dashboards ─────────────────────────

def _rango_por_defecto(dias=30):
    fin = timezone.localdate()
    return fin - timedelta(days=dias - 1), fin


def serie_diaria(fecha_ini, fecha_fin, integracion_id=None, campana_ids=None, producto_ids=None):
    """Serie por día: gasto de Meta vs. pedidos confirmados vs. entregados (eventos
    reales tomados de PedidoEditLog). Si se pasa campana_ids/producto_ids, filtra a
    esas campañas (gasto) y a los pedidos de esos productos (confirmados/entregados).
    Devuelve lista ordenada por fecha."""
    # Gasto por día
    gasto_qs = InsightDiarioMeta.objects.filter(fecha__range=(fecha_ini, fecha_fin))
    if campana_ids is not None:
        gasto_qs = gasto_qs.filter(campana_id__in=campana_ids)
    else:
        gasto_qs = gasto_qs.filter(campana__incluir_en_extraccion=True)
        if integracion_id:
            gasto_qs = gasto_qs.filter(campana__cuenta__integracion_id=integracion_id)
    gasto_por_dia = {r['fecha']: r['s'] for r in
                     gasto_qs.order_by().values('fecha').annotate(s=Sum('gasto'))}

    # Confirmados / entregados por día (cuándo el pedido alcanzó ese estado)
    logs = PedidoEditLog.objects.filter(
        campo_modificado='estado', valor_nuevo__in=[LABEL_CONFIRMADO, LABEL_ENTREGADO],
        timestamp__date__range=(fecha_ini, fecha_fin))
    if producto_ids is not None:
        ped_ids = Pedido.objects.filter(items__producto__in=producto_ids).values('id')
        logs = logs.filter(pedido_id__in=ped_ids)
    elif integracion_id:
        logs = logs.filter(pedido__integracion_id=integracion_id)
    conf_por_dia, entr_por_dia = defaultdict(int), defaultdict(int)
    for r in (logs.order_by().annotate(d=TruncDate('timestamp'))
              .values('d', 'valor_nuevo').annotate(n=Count('id'))):
        if r['valor_nuevo'] == LABEL_CONFIRMADO:
            conf_por_dia[r['d']] += r['n']
        else:
            entr_por_dia[r['d']] += r['n']

    serie = []
    dia = fecha_ini
    while dia <= fecha_fin:
        serie.append({
            'fecha': dia,
            'gasto': float(gasto_por_dia.get(dia, 0) or 0),
            'confirmados': conf_por_dia.get(dia, 0),
            'entregados': entr_por_dia.get(dia, 0),
        })
        dia += timedelta(days=1)
    return serie


def tabla_productos(fecha_ini, fecha_fin, integracion_id=None):
    """Por producto (con match a algún anuncio): gasto, atribuidos por Meta,
    confirmados reales, entregados, embudo, CPA real y ROAS real."""
    matches = (MatchProductoAnuncio.objects
               .filter(campana__incluir_en_extraccion=True)   # filtro de análisis
               .select_related('producto', 'campana', 'campana__cuenta'))
    if integracion_id:
        matches = matches.filter(campana__cuenta__integracion_id=integracion_id)

    prod_campanas = defaultdict(list)
    productos = {}
    for m in matches:
        prod_campanas[m.producto_id].append(m.campana_id)
        productos[m.producto_id] = m.producto

    filas = []
    for prod_id, campana_ids in prod_campanas.items():
        producto = productos[prod_id]
        ins = (InsightDiarioMeta.objects
               .filter(campana_id__in=campana_ids, fecha__range=(fecha_ini, fecha_fin))
               .order_by().aggregate(gasto=Sum('gasto'), result=Sum('resultados')))
        gasto = float(ins['gasto'] or 0)
        meta_atribuidos = int(ins['result'] or 0)

        base = Pedido.objects.filter(items__producto=producto,
                                     fecha_pedido__date__range=(fecha_ini, fecha_fin))
        if integracion_id:
            base = base.filter(integracion_id=integracion_id)
        base = base.distinct()
        confirmados = base.filter(estado__in=ESTADOS_CONFIRMADOS).count()
        entregados_qs = base.filter(estado=Pedido.ESTADO_ENTREGADO)
        entregados = entregados_qs.count()
        ingreso = float(entregados_qs.aggregate(s=Sum('total'))['s'] or 0)

        cpa_real = round(gasto / entregados, 2) if entregados else None
        roas_real = round(ingreso / gasto, 2) if gasto else None
        # % de caída entre etapas
        caida_conf = round((1 - confirmados / meta_atribuidos) * 100) if meta_atribuidos else None
        caida_entr = round((1 - entregados / confirmados) * 100) if confirmados else None

        filas.append({
            'producto': producto, 'gasto': gasto, 'meta_atribuidos': meta_atribuidos,
            'confirmados': confirmados, 'entregados': entregados, 'ingreso': ingreso,
            'cpa_real': cpa_real, 'roas_real': roas_real,
            'caida_conf': caida_conf, 'caida_entr': caida_entr,
            'n_anuncios': len(campana_ids),
        })
    # Orden por ROAS real (los None al final), luego por gasto
    filas.sort(key=lambda f: (f['roas_real'] is None, -(f['roas_real'] or 0), -f['gasto']))
    return filas


_SIMBOLOS = {'USD': 'US$', 'PEN': 'S/', 'EUR': '€', 'MXN': 'MX$', 'COP': 'COL$', 'CLP': 'CLP$'}


def moneda_ads(integracion_id=None):
    """Devuelve el símbolo de la moneda real del gasto de Meta (la más frecuente en los
    insights). Por defecto US$ (Meta suele facturar en USD)."""
    qs = InsightDiarioMeta.objects.exclude(moneda='')
    if integracion_id:
        qs = qs.filter(campana__cuenta__integracion_id=integracion_id)
    fila = (qs.order_by().values('moneda').annotate(n=Count('id')).order_by('-n').first())
    cod = (fila['moneda'] if fila else 'USD') or 'USD'
    return _SIMBOLOS.get(cod.upper(), cod)


def tabla_campanas(fecha_ini, fecha_fin, integracion_id=None, campana_ids=None):
    """Agrupa el gasto y las métricas de Meta por CAMPAÑA (suma de sus anuncios incluidos).
    No requiere atribución de pedidos: son las cifras que reporta Meta."""
    qs = InsightDiarioMeta.objects.filter(fecha__range=(fecha_ini, fecha_fin))
    if campana_ids is not None:
        qs = qs.filter(campana_id__in=campana_ids)
    else:
        qs = qs.filter(campana__incluir_en_extraccion=True)
        if integracion_id:
            qs = qs.filter(campana__cuenta__integracion_id=integracion_id)

    rows = (qs.order_by()
            .values('campana__campaign_id', 'campana__campaign_name')
            .annotate(gasto=Sum('gasto'), impresiones=Sum('impresiones'),
                      clicks=Sum('clicks'), resultados=Sum('resultados'),
                      n_anuncios=Count('campana', distinct=True)))
    filas = []
    for r in rows:
        gasto = float(r['gasto'] or 0)
        clicks = int(r['clicks'] or 0)
        impresiones = int(r['impresiones'] or 0)
        resultados = int(r['resultados'] or 0)
        filas.append({
            'campaign_id': r['campana__campaign_id'],
            'campaign_name': r['campana__campaign_name'] or '(sin nombre)',
            'gasto': round(gasto, 2), 'impresiones': impresiones, 'clicks': clicks,
            'resultados': resultados, 'n_anuncios': r['n_anuncios'],
            'cpc': round(gasto / clicks, 2) if clicks else None,
            'cpm': round(gasto / impresiones * 1000, 2) if impresiones else None,
            'cpr': round(gasto / resultados, 2) if resultados else None,   # costo por resultado (Meta)
        })
    filas.sort(key=lambda f: -f['gasto'])
    return filas


_DIAS_SEMANA = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']


def heatmap(fecha_ini, fecha_fin, integracion_id=None):
    """Dos matrices 7x24 (día de semana x hora): gasto de Meta y confirmaciones reales.
    Sirve para ver qué horario realmente convierte, no solo dónde hay más gasto."""
    gasto = [[0.0] * 24 for _ in range(7)]
    conf = [[0] * 24 for _ in range(7)]

    ins = InsightHorarioMeta.objects.filter(
        campana__incluir_en_extraccion=True, fecha__range=(fecha_ini, fecha_fin))
    if integracion_id:
        ins = ins.filter(campana__cuenta__integracion_id=integracion_id)
    for r in ins.order_by().values('fecha', 'hora').annotate(s=Sum('gasto')):
        wd = r['fecha'].weekday()
        h = max(0, min(23, r['hora']))
        gasto[wd][h] += float(r['s'] or 0)

    logs = PedidoEditLog.objects.filter(
        campo_modificado='estado', valor_nuevo=LABEL_CONFIRMADO,
        timestamp__date__range=(fecha_ini, fecha_fin))
    if integracion_id:
        logs = logs.filter(pedido__integracion_id=integracion_id)
    for log in logs.only('timestamp'):
        dt = timezone.localtime(log.timestamp)
        conf[dt.weekday()][dt.hour] += 1

    max_gasto = max((c for fila in gasto for c in fila), default=0) or 1
    max_conf = max((c for fila in conf for c in fila), default=0) or 1

    def _nivel(val, mx):
        if val <= 0:
            return 0
        return min(5, int(val / mx * 5) + 1)   # 1..5 según intensidad

    filas_gasto = [{'dia': _DIAS_SEMANA[wd],
                    'celdas': [{'val': round(gasto[wd][h], 2), 'nivel': _nivel(gasto[wd][h], max_gasto)}
                               for h in range(24)]} for wd in range(7)]
    filas_conf = [{'dia': _DIAS_SEMANA[wd],
                   'celdas': [{'val': conf[wd][h], 'nivel': _nivel(conf[wd][h], max_conf)}
                              for h in range(24)]} for wd in range(7)]
    return {
        'horas': list(range(24)),
        'filas_gasto': filas_gasto, 'filas_conf': filas_conf,
        'total_gasto': round(sum(c for fila in gasto for c in fila), 2),
        'total_conf': sum(c for fila in conf for c in fila),
    }


# ───────────────────────── Inicio: Gasto Meta vs Pedidos ─────────────────────────

def serie_meta_vs_pedidos(desde, hasta, integracion_id=None):
    """Serie para el gráfico del Inicio: gasto de Meta vs nº de pedidos.
    Si el rango es un solo día → granularidad por HORA (0–23, lo más fino que da Meta).
    Si abarca varios días → granularidad por DÍA. Devuelve un dict listo para Chart.js.

    A diferencia de los dashboards de análisis, aquí se muestra el gasto TOTAL de Meta
    (no se filtra por incluir_en_extraccion): el Inicio es una vista de negocio.

    Nota: la hora de los pedidos se agrupa en America/Lima; la hora de Meta es la de la
    zona del anunciante, así que el cruce horario es una aproximación de alto nivel."""
    por_hora = (desde == hasta)

    if por_hora:
        # ── Gasto Meta por hora (todo el gasto, sin filtro de análisis) ──
        gi = InsightHorarioMeta.objects.filter(fecha=desde)
        if integracion_id:
            gi = gi.filter(campana__cuenta__integracion_id=integracion_id)
        gasto_por = {r['hora']: float(r['s'] or 0)
                     for r in gi.order_by().values('hora').annotate(s=Sum('gasto'))}

        # ── Pedidos por hora (hora local de Perú) ──
        pi = Pedido.objects.filter(fecha_pedido__date=desde)
        if integracion_id:
            pi = pi.filter(integracion_id=integracion_id)
        ped_por, monto_por = defaultdict(int), defaultdict(float)
        for r in (pi.order_by().annotate(h=ExtractHour('fecha_pedido'))
                  .values('h').annotate(n=Count('id'), m=Sum('total'))):
            ped_por[r['h']] = r['n']
            monto_por[r['h']] = float(r['m'] or 0)

        labels = [f'{h:02d}h' for h in range(24)]
        gasto = [round(gasto_por.get(h, 0), 2) for h in range(24)]
        pedidos = [ped_por.get(h, 0) for h in range(24)]
        monto = [round(monto_por.get(h, 0), 2) for h in range(24)]
        granularidad = 'hora'
    else:
        # ── Gasto Meta por día (todo el gasto, sin filtro de análisis) ──
        gi = InsightDiarioMeta.objects.filter(fecha__range=(desde, hasta))
        if integracion_id:
            gi = gi.filter(campana__cuenta__integracion_id=integracion_id)
        gasto_por = {r['fecha']: float(r['s'] or 0)
                     for r in gi.order_by().values('fecha').annotate(s=Sum('gasto'))}

        # ── Pedidos por día ──
        pi = Pedido.objects.filter(fecha_pedido__date__range=(desde, hasta))
        if integracion_id:
            pi = pi.filter(integracion_id=integracion_id)
        ped_por, monto_por = defaultdict(int), defaultdict(float)
        for r in (pi.order_by().annotate(d=TruncDate('fecha_pedido'))
                  .values('d').annotate(n=Count('id'), m=Sum('total'))):
            ped_por[r['d']] = r['n']
            monto_por[r['d']] = float(r['m'] or 0)

        labels, gasto, pedidos, monto = [], [], [], []
        dia = desde
        while dia <= hasta:
            labels.append(dia.strftime('%d/%m'))
            gasto.append(round(gasto_por.get(dia, 0), 2))
            pedidos.append(ped_por.get(dia, 0))
            monto.append(round(monto_por.get(dia, 0), 2))
            dia += timedelta(days=1)
        granularidad = 'dia'

    return {
        'labels': labels,
        'gasto': gasto,
        'pedidos': pedidos,
        'monto': monto,
        'granularidad': granularidad,
        'moneda': moneda_ads(integracion_id),
        'tot_gasto': round(sum(gasto), 2),
        'tot_pedidos': sum(pedidos),
    }


# ───────────────────────── Alertas ─────────────────────────

def evaluar_alertas():
    """Calcula el CPA real diario por anuncio (con match) en la ventana configurada.
    Si supera el umbral todos los días consecutivos, dispara el webhook a n8n.
    Devuelve la lista de alertas enviadas."""
    import requests
    from .models import UmbralAlerta, AlertaEnviada

    cfg = UmbralAlerta.get_solo()
    if not cfg.activo or not cfg.n8n_webhook_url or cfg.cpa_max <= 0:
        return []

    hoy = timezone.localdate()
    n = cfg.dias_consecutivos
    ini = hoy - timedelta(days=n - 1)
    enviadas = []

    matches = MatchProductoAnuncio.objects.select_related('campana', 'producto', 'campana__cuenta')
    for m in matches:
        campana, producto = m.campana, m.producto
        if not campana.incluir_en_extraccion:
            continue
        # CPA real de cada día de la ventana
        supera_todos = True
        cpa_ultimo = None
        for i in range(n):
            dia = ini + timedelta(days=i)
            gasto = float(InsightDiarioMeta.objects.filter(campana=campana, fecha=dia)
                          .order_by().aggregate(s=Sum('gasto'))['s'] or 0)
            entregados = Pedido.objects.filter(
                items__producto=producto, fecha_pedido__date=dia,
                estado=Pedido.ESTADO_ENTREGADO).distinct().count()
            if gasto <= 0:
                supera_todos = False
                break
            cpa = gasto / entregados if entregados else float('inf')
            cpa_ultimo = cpa
            if cpa <= float(cfg.cpa_max):
                supera_todos = False
                break

        if not supera_todos:
            continue
        # No repetir la misma alerta el mismo día
        _, creada = AlertaEnviada.objects.get_or_create(
            campana=campana, fecha=hoy,
            defaults={'cpa': round(min(cpa_ultimo, 99999), 2) if cpa_ultimo != float('inf') else 0})
        if not creada:
            continue
        payload = {
            'tipo': 'cpa_alto',
            'anuncio': str(campana), 'ad_id': campana.ad_id,
            'producto': producto.nombre,
            'cuenta': campana.cuenta.nombre,
            'cpa_real': None if cpa_ultimo == float('inf') else round(cpa_ultimo, 2),
            'umbral': float(cfg.cpa_max), 'dias': n,
            'mensaje': f'⚠️ CPA real alto: {campana} ({producto.nombre}) supera S/ {cfg.cpa_max} '
                       f'durante {n} día(s).',
        }
        try:
            requests.post(cfg.n8n_webhook_url, json=payload, timeout=15)
            enviadas.append(payload)
        except requests.RequestException:
            pass

    return enviadas
