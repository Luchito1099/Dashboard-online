# anuncios/views.py
"""Vistas del módulo Publicidad (Meta Ads):
- webhook_n8n_meta: recibe los datos de n8n (firma HMAC).
- dashboard: gráfico diario, tabla por producto y heatmap (sub-pestañas).
- matching: cola de anuncios sin producto, con sugerencias difflib.
- ajustes: cuentas, qué anuncios se extraen y umbral de alerta (solo admin).
"""
import difflib
import json
from datetime import timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, HttpResponseNotAllowed
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from core.permisos import puede_ver_ads, puede_matching, puede_admin_ads, destino_vendedor
from productos.models import Producto
from integraciones.models import Integracion
from . import services
from .models import (CuentaPublicitaria, CampanaMeta, MatchProductoAnuncio, UmbralAlerta)


# ───────────────────────── Webhook n8n → ERP ─────────────────────────

@csrf_exempt
def webhook_n8n_meta(request):
    """Recibe el payload de Meta Ads desde n8n. Verifica la firma HMAC y delega en
    services.ingerir_payload (que respeta incluir_en_extraccion). Sin login: lo
    autentica la firma compartida (X-KLYNEA-Sign)."""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    firma = request.headers.get('X-KLYNEA-Sign', '')
    if not services.verificar_firma(request.body, firma):
        return HttpResponse('firma inválida', status=401)

    try:
        data = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'error': 'payload inválido'}, status=400)

    resumen = services.ingerir_payload(data)
    status = 400 if 'error' in resumen else 200
    return JsonResponse(resumen, status=status)


# ───────────────────────── Helpers de filtros ─────────────────────────

def _filtros(request):
    """Lee tienda (integración) y rango de fechas de la query."""
    from django.utils.dateparse import parse_date
    hoy = timezone.localdate()
    desde = parse_date(request.GET.get('desde', '') or '') or (hoy - timedelta(days=29))
    hasta = parse_date(request.GET.get('hasta', '') or '') or hoy
    tienda = request.GET.get('tienda', '').strip()
    integracion_id = int(tienda) if tienda.isdigit() else None
    return desde, hasta, integracion_id


def _ctx_base(request, vista):
    desde, hasta, integracion_id = _filtros(request)
    return {
        'vista': vista,
        'f_desde': desde.isoformat(), 'f_hasta': hasta.isoformat(),
        'f_tienda': str(integracion_id) if integracion_id else '',
        'tiendas': Integracion.objects.filter(categoria=Integracion.CATEGORIA_FUENTE),
        'es_admin_ads': puede_admin_ads(request.user),
        'desde': desde, 'hasta': hasta, 'integracion_id': integracion_id,
    }


# ───────────────────────── Dashboards ─────────────────────────

@login_required
def dashboard(request):
    """Página del módulo con 3 sub-pestañas: Diario / Productos / Heatmap."""
    if not puede_ver_ads(request.user):
        messages.error(request, 'No tienes permisos para ver Publicidad.')
        return redirect(destino_vendedor(request.user))

    vista = request.GET.get('vista', 'diario')
    if vista not in ('diario', 'productos', 'heatmap'):
        vista = 'diario'
    ctx = _ctx_base(request, vista)
    desde, hasta, integracion_id = ctx['desde'], ctx['hasta'], ctx['integracion_id']

    if vista == 'productos':
        ctx['filas'] = services.tabla_productos(desde, hasta, integracion_id)
    elif vista == 'heatmap':
        ctx['hm'] = services.heatmap(desde, hasta, integracion_id)
    else:
        serie = services.serie_diaria(desde, hasta, integracion_id)
        ctx['serie'] = serie
        ctx['serie_json'] = json.dumps([
            {'fecha': s['fecha'].strftime('%d/%m'), 'gasto': s['gasto'],
             'confirmados': s['confirmados'], 'entregados': s['entregados']} for s in serie])
        ctx['tot_gasto'] = round(sum(s['gasto'] for s in serie), 2)
        ctx['tot_conf'] = sum(s['confirmados'] for s in serie)
        ctx['tot_entr'] = sum(s['entregados'] for s in serie)

    # contador de matching pendiente (para el badge)
    ctx['pendientes'] = (CampanaMeta.objects.filter(incluir_en_extraccion=True, match__isnull=True)
                         .count())
    return render(request, 'anuncios/dashboard.html', ctx)


# ───────────────────────── Matching producto ↔ anuncio ─────────────────────────

@login_required
def matching_pendiente(request):
    """Anuncios marcados para extracción que aún no tienen producto asignado, con
    sugerencias automáticas (difflib) para confirmar con un click."""
    if not puede_matching(request.user):
        messages.error(request, 'No tienes permisos para hacer matching.')
        return redirect(destino_vendedor(request.user))

    pendientes = (CampanaMeta.objects
                  .filter(incluir_en_extraccion=True, match__isnull=True)
                  .select_related('cuenta', 'cuenta__integracion'))

    productos = list(Producto.objects.filter(activo=True))
    items = []
    for c in pendientes:
        texto = c.ad_name or c.adset_name or c.campaign_name
        # sugerir top-3 productos por similitud de nombre
        scored = sorted(
            ((difflib.SequenceMatcher(None, texto.lower(), p.nombre.lower()).ratio(), p)
             for p in productos), key=lambda x: x[0], reverse=True)
        sugerencias = [{'producto': p, 'score': round(r * 100)} for r, p in scored[:3] if r > 0]
        items.append({'campana': c, 'texto': texto, 'sugerencias': sugerencias})

    context = {
        'items': items,
        'productos': productos,
        'total_pendientes': len(items),
        'ya_casados': MatchProductoAnuncio.objects.count(),
    }
    return render(request, 'anuncios/matching.html', context)


@login_required
def confirmar_match(request):
    """Crea/actualiza el match de un anuncio con un producto (POST)."""
    if not puede_matching(request.user):
        return JsonResponse({'error': 'sin permiso'}, status=403)
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    campana = get_object_or_404(CampanaMeta, id=request.POST.get('campana_id'))
    producto = get_object_or_404(Producto, id=request.POST.get('producto_id'))
    es_sugerido = request.POST.get('origen') == 'sugerido'
    MatchProductoAnuncio.objects.update_or_create(
        campana=campana,
        defaults={
            'producto': producto,
            'origen': MatchProductoAnuncio.ORIGEN_SUGERIDO if es_sugerido else MatchProductoAnuncio.ORIGEN_MANUAL,
            'confianza': int(request.POST.get('score') or 100) if es_sugerido else 100,
            'creado_por': request.user,
        },
    )
    messages.success(request, f'«{campana}» casado con «{producto.nombre}».')
    return redirect('anuncios:matching')


@login_required
def quitar_match(request, campana_id):
    """Elimina el match de un anuncio (vuelve a la cola). POST."""
    if not puede_matching(request.user):
        return JsonResponse({'error': 'sin permiso'}, status=403)
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    MatchProductoAnuncio.objects.filter(campana_id=campana_id).delete()
    messages.success(request, 'Match eliminado; el anuncio vuelve a la cola.')
    return redirect('anuncios:matching')


# ───────────────────────── Ajustes (solo admin) ─────────────────────────

@login_required
def ajustes(request):
    """Cuentas publicitarias, control de qué anuncios se extraen y umbral de alerta."""
    if not puede_admin_ads(request.user):
        messages.error(request, 'Solo el administrador gestiona la configuración de Publicidad.')
        return redirect('anuncios:dashboard')

    if request.method == 'POST':
        accion = request.POST.get('accion')

        if accion == 'crear_cuenta':
            ad_account_id = request.POST.get('ad_account_id', '').strip()
            nombre = request.POST.get('nombre', '').strip()
            if ad_account_id and nombre:
                tienda = request.POST.get('integracion') or None
                defaults = {'nombre': nombre,
                            'integracion_id': int(tienda) if tienda and tienda.isdigit() else None,
                            'api_version': request.POST.get('api_version', '').strip() or 'v21.0'}
                # El token solo se actualiza si se escribió uno nuevo (no se borra al editar)
                token = request.POST.get('access_token', '').strip()
                if token:
                    defaults['access_token'] = token
                CuentaPublicitaria.objects.update_or_create(ad_account_id=ad_account_id, defaults=defaults)
                messages.success(request, 'Cuenta guardada.')
            else:
                messages.error(request, 'Falta el ad_account_id o el nombre.')

        elif accion == 'toggle_extraccion':
            ids = request.POST.getlist('incluir')   # ids marcados
            CampanaMeta.objects.update(incluir_en_extraccion=False)
            if ids:
                CampanaMeta.objects.filter(id__in=ids).update(incluir_en_extraccion=True)
            messages.success(request, 'Anuncios a extraer actualizados.')

        elif accion == 'guardar_umbral':
            from decimal import Decimal, InvalidOperation
            cfg = UmbralAlerta.get_solo()
            try:
                cfg.cpa_max = Decimal((request.POST.get('cpa_max') or '0').replace(',', '.'))
            except InvalidOperation:
                cfg.cpa_max = 0
            cfg.dias_consecutivos = max(int(request.POST.get('dias_consecutivos') or 3), 1)
            cfg.n8n_webhook_url = request.POST.get('n8n_webhook_url', '').strip()
            cfg.activo = request.POST.get('activo') == 'on'
            cfg.save()
            messages.success(request, 'Umbral de alerta guardado.')

        return redirect('anuncios:ajustes')

    cuentas = CuentaPublicitaria.objects.select_related('integracion').all()
    anuncios = (CampanaMeta.objects.select_related('cuenta')
                .order_by('cuenta__nombre', 'campaign_name', 'adset_name', 'ad_name'))
    context = {
        'cuentas': cuentas,
        'anuncios': anuncios,
        'tiendas': Integracion.objects.filter(categoria=Integracion.CATEGORIA_FUENTE),
        'umbral': UmbralAlerta.get_solo(),
    }
    return render(request, 'anuncios/ajustes.html', context)


@login_required
def probar_cuenta(request, cuenta_id):
    """Prueba la conexión directa a la Graph API de la cuenta (solo admin, POST)."""
    if not puede_admin_ads(request.user):
        return JsonResponse({'error': 'sin permiso'}, status=403)
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    from . import connectors
    cuenta = get_object_or_404(CuentaPublicitaria, id=cuenta_id)
    ok, msg = connectors.probar_conexion(cuenta)
    cuenta.ultimo_test_ok, cuenta.ultimo_test_msg, cuenta.ultimo_test_en = ok, msg[:255], timezone.now()
    cuenta.save(update_fields=['ultimo_test_ok', 'ultimo_test_msg', 'ultimo_test_en'])
    (messages.success if ok else messages.error)(request, msg)
    return redirect('anuncios:ajustes')


@login_required
def sincronizar_cuenta(request, cuenta_id):
    """Extrae los insights de la cuenta directamente desde la Graph API (solo admin, POST)."""
    if not puede_admin_ads(request.user):
        return JsonResponse({'error': 'sin permiso'}, status=403)
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    from . import connectors
    cuenta = get_object_or_404(CuentaPublicitaria, id=cuenta_id)
    try:
        dias = int(request.POST.get('dias') or 30)
    except ValueError:
        dias = 30
    ok, msg, _ = connectors.sincronizar(cuenta, dias=dias)
    cuenta.ultimo_sync_ok, cuenta.ultimo_sync_msg, cuenta.ultimo_sync_en = ok, msg[:255], timezone.now()
    cuenta.save(update_fields=['ultimo_sync_ok', 'ultimo_sync_msg', 'ultimo_sync_en'])
    (messages.success if ok else messages.error)(request, f'Sincronización: {msg}')
    return redirect('anuncios:ajustes')
