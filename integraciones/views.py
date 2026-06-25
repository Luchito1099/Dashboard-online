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
from django.db.models import Q
from django.views.decorators.csrf import csrf_exempt

# Reutilizamos el helper de permisos existente (no lo duplicamos)
from capacitacion.views import es_admin
from .models import Integracion, Pedido
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


@login_required
def pedidos_modulo(request):
    """Vista unificada de pedidos de TODAS las fuentes, con filtros, KPIs y
    edición en línea por estado (creado/confirmado/entregado/cancelado). Solo admin."""
    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos para ver los pedidos.')
        return redirect('core:home')

    qs = Pedido.objects.select_related('integracion', 'editado_por').prefetch_related('items')

    # ── Filtros ──
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

    rango = request.GET.get('rango', 'todo')
    dias = _RANGOS_FECHA.get(rango, None)
    if dias is not None:
        desde = timezone.now() - timedelta(days=dias) if dias else timezone.now().replace(
            hour=0, minute=0, second=0, microsecond=0)
        qs = qs.filter(fecha_pedido__gte=desde)

    pedidos = list(qs[:500])

    # ── KPIs (sobre lo filtrado) ──
    confirmados = [p for p in pedidos if p.estado == Pedido.ESTADO_CONFIRMADO]
    total_confirmado = sum((p.total for p in confirmados), Decimal('0'))
    total_cobrado = sum((p.adelanto for p in confirmados), Decimal('0'))
    por_cobrar = sum((p.restante for p in pedidos if p.estado != Pedido.ESTADO_CANCELADO), Decimal('0'))

    context = {
        'pedidos': pedidos,
        'total_visibles': len(pedidos),
        'num_confirmados': len(confirmados),
        'total_confirmado': total_confirmado,
        'total_cobrado': total_cobrado,
        'por_cobrar': por_cobrar,
        'estados': Pedido.ESTADO_CHOICES,
        'rangos_btn': [('hoy', 'Hoy'), ('7d', '7d'), ('30d', '30d'), ('todo', 'Todo')],
        'fuentes': Integracion.objects.filter(categoria=Integracion.CATEGORIA_FUENTE),
        'envios': sorted(Pedido.objects.exclude(tipo_envio='')
                         .values_list('tipo_envio', flat=True).distinct()),
        # Selección actual (para mantener los filtros marcados)
        'f_q': q, 'f_fuente': fuente, 'f_estado': estado, 'f_envio': envio, 'f_rango': rango,
    }
    return render(request, 'integraciones/pedidos_modulo.html', context)


@login_required
def pedido_editar(request, pedido_id):
    """Edición en línea de un pedido: estado, precio final y adelanto. Solo admin (POST, AJAX)."""
    if not es_admin(request.user):
        return JsonResponse({'error': 'sin permiso'}, status=403)
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    pedido = get_object_or_404(Pedido, id=pedido_id)
    cambios = []

    estado = request.POST.get('estado')
    if estado is not None and estado in dict(Pedido.ESTADO_CHOICES):
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
