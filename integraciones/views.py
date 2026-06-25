# integraciones/views.py
import json
import secrets
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseNotAllowed, HttpResponse, JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.db.models import Q, Count, Sum, F, Value, DecimalField, Max
from django.db.models.functions import Coalesce, Greatest, TruncDate
from django.views.decorators.csrf import csrf_exempt

# Reutilizamos el helper de permisos existente (no lo duplicamos)
from capacitacion.views import es_admin
from .models import Integracion, Pedido, PedidoSeguimiento, PedidoEditLog, registrar_cambio
from . import connectors


@login_required
def lista(request):
    """Lista de integraciones agrupadas por categoría. Solo admin."""
    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos para ver las integraciones.')
        return redirect('core:home')

    todas = list(Integracion.objects.all())
    fuentes = [i for i in todas if i.categoria == Integracion.CATEGORIA_FUENTE]
    logisticas = [i for i in todas if i.categoria == Integracion.CATEGORIA_LOGISTICA]
    context = {
        # Lista de (título de sección, items) para iterar en la plantilla
        'lista_secciones': [
            ('Fuentes de pedidos', fuentes),
            ('Empresas de logística', logisticas),
        ],
        'total': len(todas),
        'categorias': Integracion.CATEGORIA_CHOICES,
        'proveedores': Integracion.PROVEEDOR_CHOICES,
    }
    return render(request, 'integraciones/lista.html', context)


@login_required
def crear(request):
    """Crea una integración con datos básicos y redirige a la lista para completarla. Solo admin (POST)."""
    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos para crear integraciones.')
        return redirect('core:home')
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    nombre = request.POST.get('nombre', '').strip() or 'Nueva integración'
    categoria = request.POST.get('categoria', Integracion.CATEGORIA_FUENTE)
    proveedor = request.POST.get('proveedor', Integracion.PROVEEDOR_SHOPIFY)

    integ = Integracion.objects.create(
        nombre=nombre,
        categoria=categoria,
        proveedor=proveedor,
        orden=Integracion.objects.count(),
    )
    messages.success(request, f'Integración «{integ.nombre}» creada. Completa sus credenciales abajo.')
    return redirect(reverse_lista() + f'#integ-{integ.id}')


@login_required
def editar(request, integracion_id):
    """Guarda los cambios de una integración. Solo admin (POST).
    Las credenciales que lleguen vacías se conservan (no se borra el secreto al guardar)."""
    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos para editar integraciones.')
        return redirect('core:home')
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    integ = get_object_or_404(Integracion, id=integracion_id)
    integ.nombre = request.POST.get('nombre', integ.nombre).strip()
    integ.etiqueta = request.POST.get('etiqueta', integ.etiqueta).strip()
    integ.categoria = request.POST.get('categoria', integ.categoria)
    integ.proveedor = request.POST.get('proveedor', integ.proveedor)
    integ.tienda_url = request.POST.get('tienda_url', integ.tienda_url).strip()
    integ.api_version = request.POST.get('api_version', integ.api_version).strip()
    integ.scopes = request.POST.get('scopes', integ.scopes).strip()
    integ.activo = request.POST.get('activo') == 'on'

    # Credenciales: solo se actualizan si el campo viene con contenido nuevo
    for campo in ('token', 'api_key', 'api_secret'):
        nuevo = request.POST.get(campo, '').strip()
        if nuevo:
            setattr(integ, campo, nuevo)

    # Shalom: usuario (api_key) se guarda siempre; contraseña (token) solo si llega
    if integ.proveedor == 'shalom':
        integ.api_key = request.POST.get('shalom_usuario', integ.api_key).strip()
        nueva_pass = request.POST.get('shalom_password', '').strip()
        if nueva_pass:
            integ.token = nueva_pass

    integ.save()

    if integ.proveedor == 'shalom':
        _guardar_config_shalom(integ, request)

    messages.success(request, f'Integración «{integ.nombre}» actualizada.')
    return redirect(reverse_lista() + f'#integ-{integ.id}')


def _guardar_config_shalom(integ, request):
    """Guarda los ajustes específicos de Shalom en ConfigShalom."""
    from .models import ConfigShalom
    cfg, _ = ConfigShalom.objects.get_or_create(integracion=integ)
    cfg.intervalo_horas = _a_int(request.POST.get('intervalo_horas'), cfg.intervalo_horas)
    cfg.dias_atras = _a_int(request.POST.get('dias_atras'), cfg.dias_atras)
    cfg.max_paginas = _a_int(request.POST.get('max_paginas'), cfg.max_paginas)
    # horarios: coma-separados "08:00,14:00"
    horarios_raw = request.POST.get('horarios', '')
    cfg.horarios = [h.strip() for h in horarios_raw.split(',') if h.strip()]
    # selectores (JSON); si no es válido, se conserva
    sel_raw = request.POST.get('config_scraper', '').strip()
    if sel_raw:
        try:
            cfg.config_scraper = json.loads(sel_raw)
        except ValueError:
            messages.warning(request, 'Los selectores no eran JSON válido; se conservaron los anteriores.')
    cfg.usar_codigo_avanzado = request.POST.get('usar_codigo_avanzado') == 'on'
    if request.POST.get('codigo_listado', '').strip():
        cfg.codigo_listado = request.POST['codigo_listado']
    if request.POST.get('codigo_validacion', '').strip():
        cfg.codigo_validacion = request.POST['codigo_validacion']
    cfg.save()


def _a_int(valor, por_defecto):
    try:
        return int(valor)
    except (ValueError, TypeError):
        return por_defecto


@login_required
def eliminar(request, integracion_id):
    """Elimina una integración. Solo admin (POST)."""
    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos para eliminar integraciones.')
        return redirect('core:home')
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    integ = get_object_or_404(Integracion, id=integracion_id)
    nombre = integ.nombre
    integ.delete()
    messages.success(request, f'Integración «{nombre}» eliminada.')
    return redirect('integraciones:lista')


@login_required
def probar(request, integracion_id):
    """Prueba la conexión con el proveedor y guarda el resultado. Solo admin (POST)."""
    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos para probar integraciones.')
        return redirect('core:home')
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    integ = get_object_or_404(Integracion, id=integracion_id)
    ok, msg = connectors.probar_conexion(integ)
    if ok:
        messages.success(request, f'«{integ.nombre}»: {msg}')
    else:
        messages.error(request, f'«{integ.nombre}»: {msg}')
    return redirect(reverse_lista() + f'#integ-{integ.id}')


@login_required
def sincronizar(request, integracion_id):
    """Extrae los pedidos del proveedor y los guarda. Solo admin (POST)."""
    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos para sincronizar integraciones.')
        return redirect('core:home')
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    integ = get_object_or_404(Integracion, id=integracion_id)
    ok, msg, _total = connectors.extraer_pedidos(integ)
    if ok:
        messages.success(request, f'«{integ.nombre}»: {msg}')
    else:
        messages.error(request, f'«{integ.nombre}»: {msg}')
    return redirect(reverse_lista() + f'#integ-{integ.id}')


@login_required
def pedidos(request, integracion_id):
    """Lista los pedidos ya extraídos de una integración. Solo admin."""
    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos para ver los pedidos.')
        return redirect('core:home')

    integ = get_object_or_404(Integracion, id=integracion_id)
    context = {
        'integ': integ,
        'pedidos': integ.pedidos.prefetch_related('items')[:500],  # límite de seguridad
        'total': integ.pedidos.count(),
    }
    return render(request, 'integraciones/pedidos.html', context)


# ───────────────────────── Módulo Pedidos (vista unificada) ─────────────────────────

# Rangos rápidos de fecha del módulo (clave → días hacia atrás; None = sin límite)
_RANGOS_FECHA = {'hoy': 0, '7d': 7, '30d': 30, 'todo': None}

# Sub-pestañas del módulo
_VISTAS_PEDIDOS = ('listado', 'seguimiento', 'avances')


# Opciones de ordenamiento (clave → campo de order_by)
_ORDEN_PEDIDOS = {
    'reciente': '-fecha_pedido',
    'antiguo': 'fecha_pedido',
    'cliente': 'nombre_cliente',
    'numero': 'numero',
    'telefono': 'telefono',
}
_ORDEN_LABELS = [
    ('reciente', 'Más recientes'),
    ('antiguo', 'Más antiguos'),
    ('cliente', 'Cliente (A-Z)'),
    ('numero', 'Nº de pedido'),
    ('telefono', 'Teléfono'),
]


def _filtrar_pedidos(request):
    """Aplica los filtros comunes (q, fuente, estado, envío, rango, orden) y devuelve
    (queryset filtrado, dict con la selección actual de filtros)."""
    qs = Pedido.objects.select_related('integracion', 'editado_por').prefetch_related('items')

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(nombre_cliente__icontains=q) | Q(telefono__icontains=q) | Q(numero__icontains=q))

    fuente = request.GET.get('fuente', '').strip()
    if fuente:
        qs = qs.filter(integracion_id=fuente)

    estado = request.GET.get('estado', '').strip()
    if estado in dict(Pedido.ESTADO_CHOICES):
        qs = qs.filter(estado=estado)

    envio = request.GET.get('envio', '').strip()
    if envio:
        qs = qs.filter(tipo_envio=envio)

    # Rango de fechas explícito (desde / hasta) tiene prioridad sobre los botones rápidos.
    from django.utils.dateparse import parse_date
    desde = request.GET.get('desde', '').strip()
    hasta = request.GET.get('hasta', '').strip()
    d_desde = parse_date(desde) if desde else None
    d_hasta = parse_date(hasta) if hasta else None
    rango = request.GET.get('rango', 'todo')

    if d_desde or d_hasta:
        if d_desde:
            qs = qs.filter(fecha_pedido__date__gte=d_desde)
        if d_hasta:
            qs = qs.filter(fecha_pedido__date__lte=d_hasta)
        rango = ''   # los botones rápidos quedan inactivos cuando hay rango manual
    else:
        # Fechas en hora de Perú (America/Lima): usamos la fecha local y el lookup __date,
        # que Django evalúa en la zona horaria activa (TIME_ZONE). Así "Hoy" coincide con el Inicio.
        dias = _RANGOS_FECHA.get(rango, None)
        if dias is not None:
            hoy = timezone.localdate()
            if dias == 0:   # Hoy
                qs = qs.filter(fecha_pedido__date=hoy)
            else:           # Últimos N días (incluye hoy)
                qs = qs.filter(fecha_pedido__date__gte=hoy - timedelta(days=dias - 1))

    # Ordenamiento
    orden = request.GET.get('orden', 'reciente')
    campo_orden = _ORDEN_PEDIDOS.get(orden)
    if campo_orden:
        qs = qs.order_by(campo_orden)
    else:
        orden = 'reciente'

    filtros = {'f_q': q, 'f_fuente': fuente, 'f_estado': estado, 'f_envio': envio,
               'f_rango': rango, 'f_orden': orden, 'f_desde': desde, 'f_hasta': hasta}
    return qs, filtros


def _base_context(request, filtros, vista):
    """Contexto compartido por todas las sub-vistas (filtros, selectores, permisos)."""
    from core.permisos import puede_editar_seguimiento
    ctx = {
        'vista': vista,
        'estados': Pedido.ESTADO_CHOICES,
        'rangos_btn': [('hoy', 'Hoy'), ('7d', '7d'), ('30d', '30d'), ('todo', 'Todo')],
        'fuentes': Integracion.objects.filter(categoria=Integracion.CATEGORIA_FUENTE),
        'envios': sorted(Pedido.objects.exclude(tipo_envio='')
                         .values_list('tipo_envio', flat=True).distinct()),
        'ordenes': _ORDEN_LABELS,
        'puede_editar_pedidos': es_admin(request.user) or puede_editar_seguimiento(request.user),
        'puede_editar_seguimiento': puede_editar_seguimiento(request.user),
        'es_admin': es_admin(request.user),
    }
    ctx.update(filtros)
    return ctx


@login_required
def pedidos_modulo(request):
    """Módulo Pedidos con tres sub-pestañas (Listado / Seguimiento / Avances),
    persistentes en la URL (?vista=...). Admin y analista siempre; vendedor según permisos."""
    from core.permisos import (puede_ver_pedidos, destino_vendedor, puede_ver_seguimiento,
                               puede_ver_avances, puede_ver_listado, puede_ver)

    if not puede_ver_pedidos(request.user):
        messages.error(request, 'No tienes permisos para ver los pedidos.')
        return redirect(destino_vendedor(request.user))

    can_listado = puede_ver_listado(request.user)
    can_seguimiento = puede_ver_seguimiento(request.user)
    can_avances = puede_ver_avances(request.user)

    # Pestaña por defecto: la primera que el usuario pueda ver
    default_vista = 'listado' if can_listado else ('seguimiento' if can_seguimiento else 'avances')
    vista = request.GET.get('vista', default_vista)
    if vista not in _VISTAS_PEDIDOS:
        vista = default_vista
    # Si pide una pestaña sin permiso, cae a la pestaña por defecto permitida
    if (vista == 'listado' and not can_listado) or \
       (vista == 'seguimiento' and not can_seguimiento) or \
       (vista == 'avances' and not can_avances):
        vista = default_vista

    qs, filtros = _filtrar_pedidos(request)
    context = _base_context(request, filtros, vista)
    # Permisos para mostrar/ocultar pestañas
    context['tab_listado'] = can_listado
    context['tab_seguimiento'] = can_seguimiento
    context['tab_avances'] = can_avances
    # Edición de montos/estado en Listado solo con el permiso clásico
    context['puede_editar_listado'] = puede_ver(request.user, 'vendedor_puede_editar_pedidos')

    if vista == 'seguimiento':
        _context_seguimiento(qs, context)
    elif vista == 'avances':
        _context_avances(qs, context)
    else:
        _context_listado(qs, context)

    return render(request, 'integraciones/pedidos_modulo.html', context)


def _context_listado(qs, context):
    """KPIs financieros + lista de pedidos para la pestaña Listado."""
    cero = Value(Decimal('0'), output_field=DecimalField(max_digits=12, decimal_places=2))
    qs = qs.annotate(n_historial=Count('historial'))
    context['total_visibles'] = qs.count()
    conf = qs.filter(estado=Pedido.ESTADO_CONFIRMADO).aggregate(
        n=Count('id'),
        total=Coalesce(Sum('total'), cero),
        cobrado=Coalesce(Sum('adelanto'), cero),
    )
    restante_expr = Greatest(F('total') - F('adelanto'), cero)
    por_cobrar = qs.exclude(estado=Pedido.ESTADO_CANCELADO).aggregate(
        s=Coalesce(Sum(restante_expr), cero))['s']
    context.update({
        'pedidos': list(qs),
        'num_confirmados': conf['n'],
        'total_confirmado': conf['total'],
        'total_cobrado': conf['cobrado'],
        'por_cobrar': por_cobrar,
    })


def _context_seguimiento(qs, context):
    """Lista de pedidos con sus datos de seguimiento (creados al vuelo en plantilla si faltan)."""
    from capacitacion.models import Estrategia
    qs = qs.select_related('seguimiento', 'seguimiento__estrategia')
    context.update({
        'pedidos': list(qs),
        'total_visibles': qs.count(),
        'llamada_choices': PedidoSeguimiento.LLAMADA_CHOICES,
        'tipo_cliente_choices': PedidoSeguimiento.TIPO_CLIENTE_CHOICES,
        'etapa_choices': PedidoSeguimiento.ETAPA_CHOICES,
        'estrategias': Estrategia.objects.filter(activo=True),
    })


def _context_avances(qs, context):
    """KPIs/funnel agregados para la pestaña Avances."""
    cero = Value(Decimal('0'), output_field=DecimalField(max_digits=12, decimal_places=2))
    total = qs.count()

    # Conteo por estado de flujo
    cuenta_estado = {r['estado']: r['n'] for r in qs.values('estado').annotate(n=Count('id'))}
    por_estado = [(lbl, cuenta_estado.get(val, 0), val) for val, lbl in Pedido.ESTADO_CHOICES]

    # Funnel por etapa del embudo (los pedidos sin seguimiento cuentan como 'creado')
    cuenta_etapa_raw = {r['seguimiento__etapa_embudo']: r['n']
                        for r in qs.values('seguimiento__etapa_embudo').annotate(n=Count('id'))}
    sin_seg = cuenta_etapa_raw.pop(None, 0)
    cuenta_etapa = dict(cuenta_etapa_raw)
    cuenta_etapa['creado'] = cuenta_etapa.get('creado', 0) + sin_seg
    por_etapa = [(lbl, cuenta_etapa.get(val, 0), val) for val, lbl in PedidoSeguimiento.ETAPA_CHOICES]
    max_etapa = max([n for _, n, _ in por_etapa] + [1])

    # Conversión
    n_creado = cuenta_estado.get(Pedido.ESTADO_CREADO, 0)
    n_conf = cuenta_estado.get(Pedido.ESTADO_CONFIRMADO, 0)
    n_entreg = cuenta_estado.get(Pedido.ESTADO_ENTREGADO, 0)
    base_conf = total - cuenta_estado.get(Pedido.ESTADO_CANCELADO, 0)
    conv_confirmacion = round(n_conf / base_conf * 100) if base_conf else 0
    conv_entrega = round(n_entreg / n_conf * 100) if n_conf else 0

    # Por fuente
    por_fuente = list(qs.values('integracion__nombre', 'integracion__proveedor')
                      .annotate(n=Count('id')).order_by('-n'))
    max_fuente = max([r['n'] for r in por_fuente] + [1])

    # Por canal manual
    por_canal = [(dict(Pedido.FUENTE_MANUAL_CHOICES).get(r['fuente_manual'], r['fuente_manual'] or '—'), r['n'])
                 for r in qs.filter(origen=Pedido.ORIGEN_MANUAL).values('fuente_manual')
                 .annotate(n=Count('id')).order_by('-n')]

    # Evolución diaria (últimos registros con fecha)
    evol = list(qs.exclude(fecha_pedido=None).annotate(d=TruncDate('fecha_pedido'))
                .values('d').annotate(n=Count('id')).order_by('-d')[:14])
    evol.reverse()
    max_evol = max([r['n'] for r in evol] + [1])

    # Por vendedor: registros manuales + ediciones
    por_vendedor_reg = list(qs.filter(origen=Pedido.ORIGEN_MANUAL).exclude(registrado_por=None)
                            .values('registrado_por__username').annotate(n=Count('id')).order_by('-n'))
    por_editor = list(qs.exclude(editado_por=None)
                      .values('editado_por__username').annotate(n=Count('id')).order_by('-n'))

    context.update({
        'av_total': total,
        'av_por_estado': por_estado,
        'av_por_etapa': por_etapa,
        'av_max_etapa': max_etapa,
        'av_conv_confirmacion': conv_confirmacion,
        'av_conv_entrega': conv_entrega,
        'av_por_fuente': por_fuente,
        'av_max_fuente': max_fuente,
        'av_por_canal': por_canal,
        'av_evol': evol,
        'av_max_evol': max_evol,
        'av_por_vendedor_reg': por_vendedor_reg,
        'av_por_editor': por_editor,
    })


@login_required
def pedido_editar(request, pedido_id):
    """Edición en línea de un pedido: estado, precio final y adelanto (POST, AJAX).
    Admin siempre; el vendedor solo si tiene el permiso de editar pedidos.
    Cada cambio queda registrado en el historial (PedidoEditLog)."""
    from core.permisos import puede_ver
    if not puede_ver(request.user, 'vendedor_puede_editar_pedidos'):
        return JsonResponse({'error': 'sin permiso'}, status=403)
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    pedido = get_object_or_404(Pedido, id=pedido_id)
    cambios = []

    estado = request.POST.get('estado')
    if estado is not None and estado in dict(Pedido.ESTADO_CHOICES):
        if estado != pedido.estado:
            registrar_cambio(pedido, request.user, 'estado',
                             pedido.get_estado_display(), dict(Pedido.ESTADO_CHOICES)[estado])
            pedido.estado = estado
            cambios.append('estado')

    for campo in ('total', 'adelanto'):
        crudo = request.POST.get(campo)
        if crudo is None or crudo == '':
            continue
        try:
            valor = Decimal(crudo.replace(',', '.'))
        except (InvalidOperation, AttributeError):
            return JsonResponse({'error': f'Valor inválido para {campo}.'}, status=400)
        if valor < 0:
            return JsonResponse({'error': f'{campo} no puede ser negativo.'}, status=400)
        if valor != getattr(pedido, campo):
            registrar_cambio(pedido, request.user, campo, getattr(pedido, campo), valor)
            setattr(pedido, campo, valor)
            cambios.append(campo)

    if not cambios:
        return JsonResponse({'error': 'Nada que actualizar.'}, status=400)

    pedido.editado_por = request.user
    pedido.editado_en = timezone.now()
    pedido.save(update_fields=cambios + ['editado_por', 'editado_en'])

    return JsonResponse({
        'ok': True,
        'estado': pedido.estado,
        'estado_label': pedido.get_estado_display(),
        'total': f'{pedido.total:.2f}',
        'adelanto': f'{pedido.adelanto:.2f}',
        'restante': f'{pedido.restante:.2f}',
        'editado_por': request.user.get_full_name() or request.user.username,
    })


@login_required
def pedido_seguimiento_editar(request, pedido_id):
    """Edición en línea de los campos de Seguimiento (llamada, comentario, tipo de
    cliente, etapa del embudo, estrategia). POST/AJAX. Loguea cada cambio."""
    from core.permisos import puede_editar_seguimiento
    if not puede_editar_seguimiento(request.user):
        return JsonResponse({'error': 'sin permiso'}, status=403)
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    pedido = get_object_or_404(Pedido, id=pedido_id)
    seg = pedido.get_seguimiento()
    cambios = False

    # Campos de choices (validamos contra las opciones del modelo)
    choice_campos = {
        'llamada_estado': dict(PedidoSeguimiento.LLAMADA_CHOICES),
        'tipo_cliente': dict(PedidoSeguimiento.TIPO_CLIENTE_CHOICES),
        'etapa_embudo': dict(PedidoSeguimiento.ETAPA_CHOICES),
    }
    for campo, opciones in choice_campos.items():
        nuevo = request.POST.get(campo)
        if nuevo is None:
            continue
        if nuevo != '' and nuevo not in opciones:
            return JsonResponse({'error': f'Valor inválido para {campo}.'}, status=400)
        actual = getattr(seg, campo)
        if nuevo != actual:
            ant = opciones.get(actual, actual)
            nue = opciones.get(nuevo, nuevo)
            registrar_cambio(pedido, request.user, campo, ant, nue)
            setattr(seg, campo, nuevo)
            cambios = True

    # Comentario (texto libre)
    if 'comentario' in request.POST:
        nuevo = request.POST.get('comentario', '').strip()
        if nuevo != seg.comentario:
            registrar_cambio(pedido, request.user, 'comentario', seg.comentario, nuevo)
            seg.comentario = nuevo
            cambios = True

    # Llamadas intentadas (entero ≥ 0)
    if 'llamadas_intentadas' in request.POST:
        crudo = (request.POST.get('llamadas_intentadas') or '0').strip()
        try:
            nuevo = max(int(crudo), 0)
        except ValueError:
            return JsonResponse({'error': 'Número de llamadas inválido.'}, status=400)
        if nuevo != seg.llamadas_intentadas:
            registrar_cambio(pedido, request.user, 'llamadas_intentadas', seg.llamadas_intentadas, nuevo)
            seg.llamadas_intentadas = nuevo
            cambios = True

    # Estrategia (FK)
    if 'estrategia' in request.POST:
        from capacitacion.models import Estrategia
        raw = request.POST.get('estrategia', '').strip()
        nuevo_id = int(raw) if raw.isdigit() else None
        if nuevo_id != (seg.estrategia_id or None):
            ant = seg.estrategia.nombre if seg.estrategia else ''
            nueva = Estrategia.objects.filter(id=nuevo_id).first() if nuevo_id else None
            if nuevo_id and not nueva:
                return JsonResponse({'error': 'Estrategia inválida.'}, status=400)
            registrar_cambio(pedido, request.user, 'estrategia', ant, nueva.nombre if nueva else '')
            seg.estrategia = nueva
            cambios = True

    if not cambios:
        return JsonResponse({'error': 'Nada que actualizar.'}, status=400)

    seg.actualizado_por = request.user
    seg.actualizado_en = timezone.now()
    seg.save()

    return JsonResponse({
        'ok': True,
        'llamada_estado': seg.llamada_estado,
        'tipo_cliente': seg.tipo_cliente,
        'etapa_embudo': seg.etapa_embudo,
        'actualizado_por': request.user.get_full_name() or request.user.username,
    })


@login_required
def pedido_historial(request, pedido_id):
    """Devuelve el historial cronológico de cambios de un pedido (JSON para el drawer)."""
    from core.permisos import puede_ver_pedidos
    if not puede_ver_pedidos(request.user):
        return JsonResponse({'error': 'sin permiso'}, status=403)

    pedido = get_object_or_404(Pedido, id=pedido_id)
    logs = pedido.historial.select_related('usuario')[:200]
    etiquetas = {
        'estado': 'Estado', 'total': 'Precio final', 'adelanto': 'Adelanto',
        'llamada_estado': 'Llamada', 'llamadas_intentadas': 'Llamadas intentadas',
        'comentario': 'Comentario', 'tipo_cliente': 'Tipo de cliente',
        'etapa_embudo': 'Etapa del embudo', 'estrategia': 'Estrategia',
    }
    data = [{
        'id': l.id,
        'campo': etiquetas.get(l.campo_modificado, l.campo_modificado),
        'anterior': l.valor_anterior or '—',
        'nuevo': l.valor_nuevo or '—',
        'usuario': (l.usuario.get_full_name() or l.usuario.username) if l.usuario else 'Sistema',
        'cuando': timezone.localtime(l.timestamp).strftime('%d/%m/%Y %H:%M'),
    } for l in logs]
    return JsonResponse({
        'ok': True,
        'pedido': pedido.numero or pedido.external_id,
        'puede_revertir': es_admin(request.user),
        'logs': data,
    })


@login_required
def pedido_revertir(request, log_id):
    """Reaplica el valor anterior de un cambio (solo admin). Registra un log inverso."""
    if not es_admin(request.user):
        return JsonResponse({'error': 'sin permiso'}, status=403)
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    log = get_object_or_404(PedidoEditLog, id=log_id)
    pedido = log.pedido
    campo = log.campo_modificado

    # Campos del propio Pedido
    if campo == 'estado':
        inv = {v: k for k, v in Pedido.ESTADO_CHOICES}
        clave = inv.get(log.valor_anterior)
        if clave is None:
            return JsonResponse({'error': 'No se puede revertir este valor.'}, status=400)
        registrar_cambio(pedido, request.user, 'estado', pedido.get_estado_display(), log.valor_anterior)
        pedido.estado = clave
        pedido.editado_por = request.user
        pedido.editado_en = timezone.now()
        pedido.save(update_fields=['estado', 'editado_por', 'editado_en'])
    elif campo in ('total', 'adelanto'):
        try:
            valor = Decimal((log.valor_anterior or '0').replace(',', '.'))
        except (InvalidOperation, AttributeError):
            return JsonResponse({'error': 'Valor anterior inválido.'}, status=400)
        registrar_cambio(pedido, request.user, campo, getattr(pedido, campo), valor)
        setattr(pedido, campo, valor)
        pedido.editado_por = request.user
        pedido.editado_en = timezone.now()
        pedido.save(update_fields=[campo, 'editado_por', 'editado_en'])
    elif campo in ('llamada_estado', 'tipo_cliente', 'etapa_embudo', 'comentario',
                   'estrategia', 'llamadas_intentadas'):
        seg = pedido.get_seguimiento()
        if campo == 'estrategia':
            from capacitacion.models import Estrategia
            nueva = Estrategia.objects.filter(nombre=log.valor_anterior).first()
            registrar_cambio(pedido, request.user, 'estrategia',
                             seg.estrategia.nombre if seg.estrategia else '', log.valor_anterior or '')
            seg.estrategia = nueva
        else:
            mapas = {
                'llamada_estado': {v: k for k, v in PedidoSeguimiento.LLAMADA_CHOICES},
                'tipo_cliente': {v: k for k, v in PedidoSeguimiento.TIPO_CLIENTE_CHOICES},
                'etapa_embudo': {v: k for k, v in PedidoSeguimiento.ETAPA_CHOICES},
            }
            if campo == 'comentario':
                valor = log.valor_anterior
            elif campo == 'llamadas_intentadas':
                try:
                    valor = max(int(log.valor_anterior or 0), 0)
                except ValueError:
                    valor = 0
            else:
                valor = mapas[campo].get(log.valor_anterior, '')
            registrar_cambio(pedido, request.user, campo, getattr(seg, campo), log.valor_anterior)
            setattr(seg, campo, valor)
        seg.actualizado_por = request.user
        seg.actualizado_en = timezone.now()
        seg.save()
    else:
        return JsonResponse({'error': 'Campo no reversible.'}, status=400)

    return JsonResponse({'ok': True})


@login_required
def pedidos_nuevos(request):
    """Sondeo (polling) de pedidos nuevos llegados por sincronización/webhook (origen
    automático). Devuelve los pedidos con id mayor al último visto para mostrar el
    pop-up de "Nuevo pedido". Sin 'desde_id' devuelve solo el id máximo (modo init)."""
    from core.permisos import puede_ver_pedidos
    if not puede_ver_pedidos(request.user):
        return JsonResponse({'ok': False}, status=403)

    qs = Pedido.objects.filter(origen=Pedido.ORIGEN_AUTO)
    desde = request.GET.get('desde_id')
    if desde is None or not desde.isdigit():
        return JsonResponse({'ok': True, 'init': True, 'max_id': qs.aggregate(m=Max('id'))['m'] or 0})

    desde_id = int(desde)
    nuevos = list(qs.filter(id__gt=desde_id).select_related('integracion').order_by('id')[:20])
    max_id = nuevos[-1].id if nuevos else desde_id
    data = [{
        'id': p.id,
        'numero': p.numero or p.external_id,
        'cliente': p.nombre_cliente or 'Cliente',
        'fuente': p.integracion.get_proveedor_display(),
    } for p in nuevos]
    return JsonResponse({'ok': True, 'max_id': max_id, 'pedidos': data,
                         'url': reverse('integraciones:pedidos_modulo')})


# ───────────────────────── Registro de pedidos (alta manual) ─────────────────────────

@login_required
def registro_pedidos(request):
    """Listado de los pedidos dados de alta manualmente (con edición inline igual al Listado)."""
    from core.permisos import puede_registrar_pedidos, destino_vendedor, puede_ver
    if not (puede_registrar_pedidos(request.user) or es_admin(request.user)):
        messages.error(request, 'No tienes permisos para el registro de pedidos.')
        return redirect(destino_vendedor(request.user))

    qs = (Pedido.objects.filter(origen=Pedido.ORIGEN_MANUAL)
          .select_related('integracion', 'editado_por', 'registrado_por')
          .prefetch_related('items')
          .annotate(n_historial=Count('historial')))

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(nombre_cliente__icontains=q) | Q(telefono__icontains=q) | Q(numero__icontains=q))

    context = {
        'pedidos': list(qs),
        'total_visibles': qs.count(),
        'estados': Pedido.ESTADO_CHOICES,
        'f_q': q,
        'puede_editar_listado': puede_ver(request.user, 'vendedor_puede_editar_pedidos') or es_admin(request.user),
        'es_admin': es_admin(request.user),
    }
    return render(request, 'integraciones/registro_lista.html', context)


@login_required
def registro_crear(request):
    """Formulario de alta manual de un pedido. Entra al mismo pipeline (fuente 'Registro manual')."""
    from core.permisos import puede_registrar_pedidos, destino_vendedor
    if not (puede_registrar_pedidos(request.user) or es_admin(request.user)):
        messages.error(request, 'No tienes permisos para registrar pedidos.')
        return redirect(destino_vendedor(request.user))

    if request.method == 'POST':
        from .models import PedidoItem
        nombre = request.POST.get('nombre_cliente', '').strip()
        if not nombre:
            messages.error(request, 'El nombre del cliente es obligatorio.')
            return redirect('integraciones:registro_crear')

        def _dec(name):
            crudo = (request.POST.get(name) or '').strip().replace(',', '.')
            try:
                v = Decimal(crudo) if crudo else Decimal('0')
                return v if v >= 0 else Decimal('0')
            except InvalidOperation:
                return Decimal('0')

        fuente_manual = request.POST.get('fuente_manual', '').strip()
        if fuente_manual not in dict(Pedido.FUENTE_MANUAL_CHOICES):
            fuente_manual = Pedido.FUENTE_MANUAL_OTRO

        # Tipo de envío: Agencia / Delivery / Otros (con detalle libre si Otros)
        tipo_envio = request.POST.get('tipo_envio', '').strip()
        if tipo_envio == 'Otros':
            tipo_envio = request.POST.get('tipo_envio_otro', '').strip() or 'Otros'

        integ = Integracion.get_manual()
        pedido = Pedido.objects.create(
            integracion=integ,
            external_id=f'manual-{secrets.token_hex(6)}',
            origen=Pedido.ORIGEN_MANUAL,
            numero=request.POST.get('numero', '').strip(),
            nombre_cliente=nombre,
            telefono=request.POST.get('telefono', '').strip(),
            total=_dec('total'),
            adelanto=_dec('adelanto'),
            tipo_envio=tipo_envio,
            fuente_manual=fuente_manual,
            fuente_manual_detalle=request.POST.get('fuente_manual_detalle', '').strip(),
            registrado_por=request.user,
            editado_por=request.user,
            editado_en=timezone.now(),
            fecha_pedido=timezone.now(),
        )
        # Productos (una línea por nombre no vacío)
        nombres = request.POST.getlist('item_nombre')
        cantidades = request.POST.getlist('item_cantidad')
        precios = request.POST.getlist('item_precio')
        for i, nom in enumerate(nombres):
            nom = (nom or '').strip()
            if not nom:
                continue
            try:
                cant = int(cantidades[i]) if i < len(cantidades) and cantidades[i] else 1
            except ValueError:
                cant = 1
            try:
                prec = Decimal((precios[i] or '0').replace(',', '.')) if i < len(precios) else Decimal('0')
            except InvalidOperation:
                prec = Decimal('0')
            PedidoItem.objects.create(pedido=pedido, nombre=nom, cantidad=max(cant, 1), precio=prec)

        registrar_cambio(pedido, request.user, 'creado', '', f'Pedido manual de {nombre}')
        messages.success(request, f'Pedido manual de «{nombre}» registrado.')
        return redirect('integraciones:registro_pedidos')

    context = {
        'fuentes_manual': Pedido.FUENTE_MANUAL_CHOICES,
        'envios': sorted(Pedido.objects.exclude(tipo_envio='')
                         .values_list('tipo_envio', flat=True).distinct()),
    }
    return render(request, 'integraciones/registro_crear.html', context)


# ───────────────────────── OAuth de Shopify ─────────────────────────

@login_required
def oauth_iniciar(request, integracion_id):
    """Inicia el flujo OAuth: redirige al usuario a Shopify para autorizar la app. Solo admin."""
    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos.')
        return redirect('core:home')

    integ = get_object_or_404(Integracion, id=integracion_id)
    if integ.proveedor != 'shopify':
        messages.error(request, 'El OAuth solo aplica a integraciones Shopify.')
        return redirect(reverse_lista() + f'#integ-{integ.id}')
    if not (integ.api_key and integ.api_secret and integ.tienda_url):
        messages.error(request, 'Guarda primero el Client ID, Client Secret y subdominio antes de conectar.')
        return redirect(reverse_lista() + f'#integ-{integ.id}')

    state = secrets.token_urlsafe(24)
    request.session['shopify_oauth'] = {'state': state, 'integ_id': integ.id}
    redirect_uri = request.build_absolute_uri(reverse('integraciones:oauth_callback'))
    return redirect(connectors.construir_url_autorizacion(integ, redirect_uri, state))


@login_required
def oauth_callback(request):
    """Recibe la respuesta de Shopify, valida y guarda el access token. Solo admin."""
    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos.')
        return redirect('core:home')

    datos = request.session.get('shopify_oauth') or {}
    integ = get_object_or_404(Integracion, id=datos.get('integ_id'))

    # Validación de seguridad: state (anti-CSRF) y hmac (firma de Shopify)
    if not datos.get('state') or request.GET.get('state') != datos.get('state'):
        messages.error(request, 'Validación de seguridad fallida (state). Intenta de nuevo.')
        return redirect(reverse_lista() + f'#integ-{integ.id}')
    if not connectors.verificar_hmac(request.GET.dict(), integ.api_secret):
        messages.error(request, 'Validación de seguridad fallida (hmac). Revisa el Client Secret.')
        return redirect(reverse_lista() + f'#integ-{integ.id}')

    token = connectors.intercambiar_codigo(integ, request.GET.get('code'))
    request.session.pop('shopify_oauth', None)
    if not token:
        messages.error(request, 'No se pudo obtener el access token de Shopify.')
        return redirect(reverse_lista() + f'#integ-{integ.id}')

    integ.token = token
    integ.save()
    messages.success(request, f'«{integ.nombre}» conectada con Shopify correctamente.')
    return redirect(reverse_lista() + f'#integ-{integ.id}')


# ───────────────────────── Webhooks (tiempo real) ─────────────────────────

@login_required
def activar_webhook(request, integracion_id):
    """Registra los webhooks en Shopify para recibir pedidos nuevos en tiempo real. Solo admin (POST)."""
    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos.')
        return redirect('core:home')
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    integ = get_object_or_404(Integracion, id=integracion_id)
    if integ.proveedor != 'shopify':
        messages.error(request, 'Los webhooks solo aplican a Shopify por ahora.')
        return redirect(reverse_lista() + f'#integ-{integ.id}')

    address = request.build_absolute_uri(reverse('integraciones:webhook', args=[integ.id]))
    if address.startswith('http://'):
        messages.error(request, 'Shopify requiere una URL HTTPS pública. Activa esto en producción.')
        return redirect(reverse_lista() + f'#integ-{integ.id}')

    ok, msg = connectors.registrar_webhooks_shopify(integ, address)
    (messages.success if ok else messages.error)(request, f'«{integ.nombre}»: {msg}')
    return redirect(reverse_lista() + f'#integ-{integ.id}')


@csrf_exempt
def webhook_shopify(request, integracion_id):
    """Receptor de webhooks de Shopify (orders/create, orders/updated).
    Verifica la firma HMAC y guarda/actualiza el pedido. Sin login: lo autentica la firma."""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    integ = get_object_or_404(Integracion, id=integracion_id)
    firma = request.headers.get('X-Shopify-Hmac-Sha256', '')
    if not connectors.verificar_webhook(request.body, firma, integ.api_secret):
        return HttpResponse('firma inválida', status=401)

    try:
        pedido = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return HttpResponse('payload inválido', status=400)

    connectors._guardar_pedido_shopify(integ, pedido)
    return HttpResponse(status=200)


# ───────────────────────── Shalom (rastreo) ─────────────────────────

def _lanzar_shalom(args):
    """Lanza el comando shalom_actualizar como subproceso desacoplado (segundo plano)."""
    import subprocess
    import sys
    from django.conf import settings
    manage = str(settings.BASE_DIR / 'manage.py')
    subprocess.Popen([sys.executable, manage, 'shalom_actualizar'] + args, cwd=str(settings.BASE_DIR))


@login_required
def shalom_envios(request, integracion_id):
    """Panel de envíos Shalom: estado, alertas y lista. Solo admin."""
    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos.')
        return redirect('core:home')
    from .models import ConfigShalom
    integ = get_object_or_404(Integracion, id=integracion_id, proveedor='shalom')
    cfg, _ = ConfigShalom.objects.get_or_create(integracion=integ)
    return render(request, 'integraciones/shalom_envios.html', {'integ': integ, 'cfg': cfg})


@login_required
def api_shalom_envios(request, integracion_id):
    """Lista de envíos (JSON) con filtros: ?q=&estado=pendiente|entregado|alerta."""
    if not es_admin(request.user):
        return JsonResponse({'error': 'sin permiso'}, status=403)
    integ = get_object_or_404(Integracion, id=integracion_id, proveedor='shalom')
    from .shalom_runner import TERMINAL_REGEX
    qs = integ.envios.all()
    filtro = request.GET.get('estado', '')
    if filtro == 'transito':
        qs = qs.filter(estado_real__iregex=r'en tr[aá]nsito')
    elif filtro == 'agencia':
        qs = qs.filter(estado_real__icontains='agencia')
    elif filtro == 'destino':
        qs = qs.filter(estado_real__icontains='en destino')
    elif filtro == 'entregado':
        qs = qs.filter(entregado=True)
    elif filtro == 'pendiente':
        qs = qs.filter(entregado=False).exclude(estado_real__iregex=TERMINAL_REGEX)
    elif filtro == 'cerrado':
        qs = qs.filter(estado_real__iregex=TERMINAL_REGEX)
    elif filtro == 'alerta':
        qs = qs.filter(en_alerta=True)
    q = request.GET.get('q', '').strip()
    if q:
        from django.db.models import Q
        qs = qs.filter(Q(nombre__icontains=q) | Q(orden__icontains=q) |
                       Q(codigo__icontains=q) | Q(dni__icontains=q))
    return JsonResponse({
        'envios': [e.to_dict() for e in qs[:500]],
        'alertas': integ.envios.filter(en_alerta=True).count(),
    })


@login_required
def api_shalom_estado(request, integracion_id):
    """Estado de la corrida (para polling)."""
    if not es_admin(request.user):
        return JsonResponse({'error': 'sin permiso'}, status=403)
    from datetime import timedelta
    from django.utils import timezone
    from .models import ConfigShalom
    integ = get_object_or_404(Integracion, id=integracion_id, proveedor='shalom')
    cfg, _ = ConfigShalom.objects.get_or_create(integracion=integ)
    # Una corrida sin latido reciente está muerta (redeploy/crash): la reportamos
    # como detenida para que la UI no se quede en "Corriendo…" para siempre.
    vivo = cfg.latido and (timezone.now() - cfg.latido) < timedelta(minutes=5)
    corriendo = cfg.corriendo and vivo
    return JsonResponse({
        'corriendo': corriendo,
        'progreso': cfg.progreso,
        'zombie': bool(cfg.corriendo and not vivo),
        'ultima_corrida': cfg.ultima_corrida.strftime('%d/%m/%Y %H:%M') if cfg.ultima_corrida else '',
        'ultimo_resultado': cfg.ultimo_resultado,
    })


@login_required
def api_shalom_actualizar(request, integracion_id):
    """Lanza una corrida manual en segundo plano. Solo admin (POST).
    ?solo=validar → salta la etapa 1 (no re-descarga el listado) y valida lo que
    ya está en la base. ?solo=importar → solo descarga el listado."""
    if not es_admin(request.user):
        return JsonResponse({'error': 'sin permiso'}, status=403)
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    integ = get_object_or_404(Integracion, id=integracion_id, proveedor='shalom')
    args = ['--integracion', str(integ.id), '--manual']
    solo = request.GET.get('solo', '')
    if solo == 'validar':
        args.append('--solo-validar')
        msg = 'Validación (etapa 2) iniciada en segundo plano.'
    elif solo == 'importar':
        args.append('--solo-importar')
        msg = 'Importación (etapa 1) iniciada en segundo plano.'
    else:
        msg = 'Actualización completa iniciada en segundo plano.'
    _lanzar_shalom(args)
    return JsonResponse({'ok': True, 'mensaje': msg})


@login_required
def api_shalom_validar(request, envio_id):
    """Re-valida un envío puntual en segundo plano. Solo admin (POST)."""
    if not es_admin(request.user):
        return JsonResponse({'error': 'sin permiso'}, status=403)
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    from .models import EnvioShalom
    envio = get_object_or_404(EnvioShalom, id=envio_id)
    _lanzar_shalom(['--integracion', str(envio.integracion_id),
                    '--solo-validar', '--orden', envio.orden, '--codigo', envio.codigo])
    return JsonResponse({'ok': True, 'mensaje': 'Re-validación iniciada.'})


@login_required
def api_shalom_detener(request, integracion_id):
    """Marca la bandera para detener una corrida en curso. Solo admin (POST)."""
    if not es_admin(request.user):
        return JsonResponse({'error': 'sin permiso'}, status=403)
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    from .models import ConfigShalom
    integ = get_object_or_404(Integracion, id=integracion_id, proveedor='shalom')
    cfg, _ = ConfigShalom.objects.get_or_create(integracion=integ)
    cfg.cancelar = True
    cfg.save(update_fields=['cancelar'])
    return JsonResponse({'ok': True, 'mensaje': 'Se detendrá tras el envío en curso.'})


@login_required
def api_shalom_importar(request, integracion_id):
    """Importa envíos desde un JSON (lista de objetos del scraper). Solo admin (POST, multipart)."""
    if not es_admin(request.user):
        return JsonResponse({'error': 'sin permiso'}, status=403)
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    from .models import EnvioShalom, ConfigShalom
    from . import shalom_runner as runner
    from .shalom_scraper import parse_fecha

    integ = get_object_or_404(Integracion, id=integracion_id, proveedor='shalom')
    archivo = request.FILES.get('archivo')
    if not archivo:
        return JsonResponse({'error': 'No se envió ningún archivo.'}, status=400)
    try:
        datos = json.loads(archivo.read().decode('utf-8'))
    except (ValueError, UnicodeDecodeError) as e:
        return JsonResponse({'error': f'JSON inválido: {e}'}, status=400)
    if not isinstance(datos, list):
        return JsonResponse({'error': 'El JSON debe ser una lista de envíos.'}, status=400)

    fix = runner.arreglar_mojibake
    nuevos = actualizados = 0
    for d in datos:
        orden = str(d.get('orden', '')).strip()
        codigo = str(d.get('codigo', '')).strip()
        if not orden or not codigo:
            continue
        envio, creado = EnvioShalom.objects.update_or_create(
            integracion=integ, orden=orden, codigo=codigo,
            defaults={
                'estado': fix(d.get('estado', '')),
                'estado_real': fix(d.get('estado_real', '')),
                'producto': fix(d.get('producto', '')),
                'nombre': fix(d.get('nombre', '')),
                'dni': d.get('dni', ''),
                'monto': d.get('monto', ''),
                'lugar_entrega': fix(d.get('lugar_entrega', '')),
                'tipo_envio': fix(d.get('tipo_envio', '')),
                'fecha_texto': d.get('fecha', ''),
                'fecha_pedido': parse_fecha(d.get('fecha', '')),
            },
        )
        # Respetar entregado del JSON; calcular alerta por estado_real
        envio.entregado = bool(d.get('entregado'))
        runner._aplicar_estado(envio, envio.estado_real)
        if d.get('entregado'):
            envio.entregado = True
            envio.en_alerta = False
        envio.save()
        nuevos += 1 if creado else 0
        actualizados += 0 if creado else 1

    # Recalcular corte tras importar
    cfg, _ = ConfigShalom.objects.get_or_create(integracion=integ)
    runner._recalcular_corte(integ, cfg)
    return JsonResponse({'ok': True, 'mensaje': f'{nuevos} nuevos, {actualizados} actualizados.'})


@login_required
def api_shalom_notificar(request, envio_id):
    """Marca un envío como notificado (baja la alerta). Solo admin (POST)."""
    if not es_admin(request.user):
        return JsonResponse({'error': 'sin permiso'}, status=403)
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    from .models import EnvioShalom
    envio = get_object_or_404(EnvioShalom, id=envio_id)
    envio.notificado = True
    envio.en_alerta = False
    envio.save(update_fields=['notificado', 'en_alerta'])
    return JsonResponse({'ok': True})


def reverse_lista():
    """URL de la lista (helper para concatenar anclas #integ-<id>)."""
    return reverse('integraciones:lista')
