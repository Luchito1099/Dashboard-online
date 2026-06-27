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
from django.urls import reverse
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
    autentica la firma compartida (X-Dashboard-Sign)."""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    firma = request.headers.get('X-Dashboard-Sign', '')
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
    f_proyecto = request.GET.get('proyecto', '').strip()
    f_campana = request.GET.get('campana', '').strip()

    cqs = CampanaMeta.objects.filter(incluir_en_extraccion=True)
    if integracion_id:
        cqs = cqs.filter(cuenta__integracion_id=integracion_id)
    proyectos = sorted(set(cqs.exclude(proyecto='').values_list('proyecto', flat=True)))
    campanas = list(cqs.order_by('campaign_name').values('campaign_id', 'campaign_name').distinct())

    return {
        'vista': vista,
        'f_desde': desde.isoformat(), 'f_hasta': hasta.isoformat(),
        'f_tienda': str(integracion_id) if integracion_id else '',
        'f_proyecto': f_proyecto, 'f_campana': f_campana,
        'tiendas': Integracion.objects.filter(categoria=Integracion.CATEGORIA_FUENTE),
        'proyectos': proyectos, 'campanas_lista': campanas,
        'es_admin_ads': puede_admin_ads(request.user),
        'moneda': services.moneda_ads(integracion_id),
        'desde': desde, 'hasta': hasta, 'integracion_id': integracion_id,
    }


def _filtro_campanas(integracion_id, f_proyecto, f_campana):
    """Devuelve (campana_ids, producto_ids) según los filtros de proyecto/campaña, o
    (None, None) si no hay filtro activo (todo)."""
    if not f_proyecto and not f_campana:
        return None, None
    cqs = CampanaMeta.objects.filter(incluir_en_extraccion=True)
    if integracion_id:
        cqs = cqs.filter(cuenta__integracion_id=integracion_id)
    if f_proyecto:
        cqs = cqs.filter(proyecto=f_proyecto)
    if f_campana:
        cqs = cqs.filter(campaign_id=f_campana)
    campana_ids = list(cqs.values_list('id', flat=True))
    producto_ids = list(MatchProductoAnuncio.objects.filter(campana_id__in=campana_ids)
                        .values_list('producto_id', flat=True))
    return campana_ids, producto_ids


# ───────────────────────── Dashboards ─────────────────────────

def _auto_sync_si_necesario():
    """Dispara sincronización en background para cuentas con >15 min sin actualizar.
    Se llama desde dashboard(); no bloquea el request."""
    limite = timezone.now() - timedelta(minutes=30)
    from django.db.models import Q
    cuentas = CuentaPublicitaria.objects.filter(activo=True).exclude(access_token='').filter(
        Q(ultimo_sync_en__isnull=True) | Q(ultimo_sync_en__lt=limite)
    )
    for cuenta in cuentas:
        cuenta.ultimo_sync_ok = None
        cuenta.ultimo_sync_msg = 'Sincronizando automáticamente…'
        cuenta.ultimo_sync_en = timezone.now()
        cuenta.save(update_fields=['ultimo_sync_ok', 'ultimo_sync_msg', 'ultimo_sync_en'])
        _sync_en_hilo(cuenta.id, dias=3)


@login_required
def dashboard(request):
    """Página del módulo con 3 sub-pestañas: Diario / Productos / Heatmap."""
    if not puede_ver_ads(request.user):
        messages.error(request, 'No tienes permisos para ver Publicidad.')
        return redirect(destino_vendedor(request.user))

    # Filtro fijado por el usuario: al entrar sin parámetros, se aplica solo.
    from core.models import Perfil
    perfil, _ = Perfil.objects.get_or_create(usuario=request.user)
    if not request.GET and perfil.ads_filtro:
        return redirect(f"{reverse('anuncios:dashboard')}?{perfil.ads_filtro}")

    # Auto-sync: si alguna cuenta tiene >30 min sin actualizar, dispara en background
    _auto_sync_si_necesario()

    vista = request.GET.get('vista', 'diario')
    if vista not in ('diario', 'productos', 'heatmap'):
        vista = 'diario'
    ctx = _ctx_base(request, vista)
    desde, hasta, integracion_id = ctx['desde'], ctx['hasta'], ctx['integracion_id']
    campana_ids, producto_ids = _filtro_campanas(integracion_id, ctx['f_proyecto'], ctx['f_campana'])

    if vista == 'productos':
        ctx['filas'] = services.tabla_productos(desde, hasta, integracion_id, campana_ids)
    elif vista == 'heatmap':
        ctx['hm'] = services.heatmap(desde, hasta, integracion_id)
    else:
        serie = services.serie_diaria(desde, hasta, integracion_id, campana_ids, producto_ids)
        ctx['serie'] = serie
        ctx['serie_json'] = json.dumps([
            {'fecha': s['fecha'].strftime('%d/%m'), 'gasto': s['gasto'],
             'confirmados': s['confirmados'], 'despachados': s['despachados'],
             'entregados': s['entregados']} for s in serie])
        ctx['tot_gasto'] = round(sum(s['gasto'] for s in serie), 2)
        ctx['tot_conf'] = sum(s['confirmados'] for s in serie)
        ctx['tot_desp'] = sum(s['despachados'] for s in serie)
        ctx['tot_entr'] = sum(s['entregados'] for s in serie)
        ctx['campanas'] = services.tabla_campanas(desde, hasta, integracion_id, campana_ids)
        ctx['hay_datos'] = ctx['tot_gasto'] > 0 or ctx['tot_conf'] > 0

    # contador de matching pendiente (para el badge)
    ctx['pendientes'] = (CampanaMeta.objects.filter(incluir_en_extraccion=True, match__isnull=True)
                         .count())
    ctx['filtro_fijado'] = bool(perfil.ads_filtro)
    return render(request, 'anuncios/dashboard.html', ctx)


@login_required
def api_inicio_serie(request):
    """JSON para el gráfico del Inicio (Gasto Meta vs Pedidos). Protegido: solo quien
    puede ver Publicidad (el gasto es sensible).

    El rango lo calcula el SERVIDOR en hora de Perú (America/Lima) según ?modo=:
      - 'hoy' (default): solo hoy → granularidad por hora.
      - '7d': últimos 7 días (incluye hoy) → por día.
      - 'rango': usa ?desde=&hasta= (YYYY-MM-DD, fechas de calendario locales).
    Así "hoy"/"7d" no dependen de la zona horaria del navegador."""
    if not puede_ver_ads(request.user):
        return JsonResponse({'error': 'sin permiso'}, status=403)

    from django.utils.dateparse import parse_date
    hoy = timezone.localdate()
    modo = request.GET.get('modo', 'hoy')

    if modo == '7d':
        desde, hasta = hoy - timedelta(days=6), hoy
    elif modo == 'rango':
        desde = parse_date(request.GET.get('desde', '') or '') or hoy
        hasta = parse_date(request.GET.get('hasta', '') or '') or desde
        if hasta < desde:
            desde, hasta = hasta, desde
    else:   # hoy
        desde = hasta = hoy

    tipo = request.GET.get('tipo', 'todos')
    if tipo not in ('todos', 'preventa', 'venta'):
        tipo = 'todos'

    _auto_sync_si_necesario()
    return JsonResponse(services.serie_meta_vs_pedidos(desde, hasta, tipo=tipo))


@login_required
def api_inicio_heatmap(request):
    """JSON para el mapa de calor del Inicio (pedidos y gasto por día×hora). Protegido
    con puede_ver_ads. Agrega sobre las últimas N semanas (?semanas=4, default 4)."""
    if not puede_ver_ads(request.user):
        return JsonResponse({'error': 'sin permiso'}, status=403)

    try:
        semanas = int(request.GET.get('semanas', 4))
    except ValueError:
        semanas = 4
    semanas = max(1, min(semanas, 26))

    hoy = timezone.localdate()
    desde = hoy - timedelta(days=semanas * 7 - 1)
    return JsonResponse(services.heatmap_pedidos_hora(desde, hoy))


@login_required
def fijar_filtro(request):
    """Fija (o limpia) el filtro del dashboard de Publicidad para el usuario actual.
    POST con 'qs' = querystring a recordar (vacío = limpiar). Espejo de
    integraciones.views.pedido_filtro."""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    if not puede_ver_ads(request.user):
        return JsonResponse({'error': 'sin permiso'}, status=403)
    from core.models import Perfil
    perfil, _ = Perfil.objects.get_or_create(usuario=request.user)
    perfil.ads_filtro = (request.POST.get('qs') or '').strip().lstrip('?')[:2000]
    perfil.save(update_fields=['ads_filtro'])
    return JsonResponse({'ok': True, 'fijado': bool(perfil.ads_filtro)})


# ───────────────────────── Matching producto ↔ anuncio ─────────────────────────

@login_required
def matching_pendiente(request):
    """Anuncios marcados para análisis que aún no tienen producto asignado, con
    sugerencias automáticas (difflib). Se puede filtrar por campaña y asignar una
    campaña completa a un producto (suele ser una campaña por producto)."""
    if not puede_matching(request.user):
        messages.error(request, 'No tienes permisos para hacer matching.')
        return redirect(destino_vendedor(request.user))

    base = (CampanaMeta.objects
            .filter(incluir_en_extraccion=True, match__isnull=True)
            .select_related('cuenta', 'cuenta__integracion'))

    # Proyectos y campañas disponibles en la cola (para los filtros)
    proyectos_filtro = sorted(set(base.exclude(proyecto='')
                                  .values_list('proyecto', flat=True)))
    campanas_filtro = (base.order_by('campaign_name')
                       .values('campaign_id', 'campaign_name').distinct())

    f_proyecto = request.GET.get('proyecto', '').strip()
    f_campana = request.GET.get('campana', '').strip()
    pendientes = base
    if f_proyecto:
        pendientes = pendientes.filter(proyecto=f_proyecto)
    if f_campana:
        pendientes = pendientes.filter(campaign_id=f_campana)
    pendientes = pendientes.order_by('proyecto', 'campaign_name', 'ad_name')

    productos = list(Producto.objects.filter(activo=True))
    items = []
    for c in pendientes:
        texto = c.ad_name or c.adset_name or c.campaign_name
        scored = sorted(
            ((difflib.SequenceMatcher(None, texto.lower(), p.nombre.lower()).ratio(), p)
             for p in productos), key=lambda x: x[0], reverse=True)
        sugerencias = [{'producto': p, 'score': round(r * 100)} for r, p in scored[:3] if r > 0]
        items.append({'campana': c, 'texto': texto, 'sugerencias': sugerencias})

    # Matches ya confirmados (para la sección "Ya casados")
    casados = (MatchProductoAnuncio.objects
               .select_related('campana', 'campana__cuenta', 'producto')
               .order_by('producto__nombre', 'campana__campaign_name'))

    context = {
        'items': items,
        'productos': productos,
        'total_pendientes': len(items),
        'ya_casados': casados.count(),
        'casados': casados,
        'campanas_filtro': campanas_filtro,
        'proyectos_filtro': proyectos_filtro,
        'f_campana': f_campana, 'f_proyecto': f_proyecto,
    }
    return render(request, 'anuncios/matching.html', context)


@login_required
def confirmar_match_campana(request):
    """Asigna un producto a TODOS los anuncios pendientes de una campaña (POST)."""
    if not puede_matching(request.user):
        return JsonResponse({'error': 'sin permiso'}, status=403)
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    campaign_id = request.POST.get('campaign_id', '').strip()
    producto = get_object_or_404(Producto, id=request.POST.get('producto_id'))
    pendientes = CampanaMeta.objects.filter(
        incluir_en_extraccion=True, match__isnull=True, campaign_id=campaign_id)
    n = 0
    for c in pendientes:
        MatchProductoAnuncio.objects.update_or_create(
            campana=c, defaults={'producto': producto, 'origen': MatchProductoAnuncio.ORIGEN_MANUAL,
                                 'confianza': 100, 'creado_por': request.user})
        n += 1
    messages.success(request, f'{n} anuncio(s) de la campaña casados con «{producto.nombre}».')
    return redirect('anuncios:matching')


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
            # Etiquetas por anuncio (campos etiqueta_<id>)
            for clave, valor in request.POST.items():
                if clave.startswith('etiqueta_'):
                    cid = clave[len('etiqueta_'):]
                    if cid.isdigit():
                        CampanaMeta.objects.filter(id=cid).update(etiqueta=valor.strip()[:60])
                # Proyecto por campaña (aplica a todos los anuncios de esa campaña)
                elif clave.startswith('proyecto_camp_'):
                    campaign_id = clave[len('proyecto_camp_'):]
                    if campaign_id:
                        CampanaMeta.objects.filter(campaign_id=campaign_id).update(proyecto=valor.strip()[:80])
            messages.success(request, 'Anuncios actualizados (selección, etiquetas y proyectos).')

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
    # Ordenado por campaña para agrupar con {% regroup %} en la plantilla
    anuncios = (CampanaMeta.objects.select_related('cuenta')
                .order_by('campaign_name', 'adset_name', 'ad_name'))
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


def _sync_en_hilo(cuenta_id, dias):
    """Corre la sincronización en un hilo aparte (no bloquea el request web). Actualiza
    el estado de la cuenta al terminar y cierra su conexión de BD."""
    import threading
    from django.db import connection

    def _run():
        try:
            from . import connectors
            cuenta = CuentaPublicitaria.objects.get(id=cuenta_id)
            ok, msg, _ = connectors.sincronizar(cuenta, dias=dias)
            cuenta.ultimo_sync_ok, cuenta.ultimo_sync_msg = ok, msg[:255]
            cuenta.ultimo_sync_en = timezone.now()
            cuenta.save(update_fields=['ultimo_sync_ok', 'ultimo_sync_msg', 'ultimo_sync_en'])
        except Exception as e:   # noqa: BLE001 — registramos cualquier fallo en el estado
            try:
                cuenta = CuentaPublicitaria.objects.get(id=cuenta_id)
                cuenta.ultimo_sync_ok = False
                cuenta.ultimo_sync_msg = str(e)[:255]
                cuenta.ultimo_sync_en = timezone.now()
                cuenta.save(update_fields=['ultimo_sync_ok', 'ultimo_sync_msg', 'ultimo_sync_en'])
            except Exception:
                pass
        finally:
            connection.close()

    threading.Thread(target=_run, daemon=True).start()


@login_required
def sincronizar_cuenta(request, cuenta_id):
    """Lanza la extracción de insights desde la Graph API EN SEGUNDO PLANO (solo admin,
    POST). El request vuelve enseguida; la sync sigue corriendo y actualiza el estado."""
    if not puede_admin_ads(request.user):
        return JsonResponse({'error': 'sin permiso'}, status=403)
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    cuenta = get_object_or_404(CuentaPublicitaria, id=cuenta_id)
    try:
        dias = int(request.POST.get('dias') or 30)
    except ValueError:
        dias = 30

    # Marca "en progreso" y dispara el hilo
    cuenta.ultimo_sync_ok = None
    cuenta.ultimo_sync_msg = f'Sincronizando {dias} día(s) en segundo plano…'
    cuenta.ultimo_sync_en = timezone.now()
    cuenta.save(update_fields=['ultimo_sync_ok', 'ultimo_sync_msg', 'ultimo_sync_en'])
    _sync_en_hilo(cuenta.id, dias)

    messages.success(request, f'Sincronización de {dias} día(s) iniciada en segundo plano. '
                              'Recarga en unos minutos para ver el resultado.')
    return redirect('anuncios:ajustes')
