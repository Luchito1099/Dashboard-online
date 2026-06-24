# integraciones/views.py
import json
import secrets

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseNotAllowed, HttpResponse, JsonResponse
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

# Reutilizamos el helper de permisos existente (no lo duplicamos)
from capacitacion.views import es_admin
from .models import Integracion
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
    qs = integ.envios.all()
    filtro = request.GET.get('estado', '')
    if filtro == 'pendiente':
        qs = qs.filter(entregado=False)
    elif filtro == 'entregado':
        qs = qs.filter(entregado=True)
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
    from .models import ConfigShalom
    integ = get_object_or_404(Integracion, id=integracion_id, proveedor='shalom')
    cfg, _ = ConfigShalom.objects.get_or_create(integracion=integ)
    return JsonResponse({
        'corriendo': cfg.corriendo,
        'ultima_corrida': cfg.ultima_corrida.strftime('%d/%m/%Y %H:%M') if cfg.ultima_corrida else '',
        'ultimo_resultado': cfg.ultimo_resultado,
    })


@login_required
def api_shalom_actualizar(request, integracion_id):
    """Lanza una corrida manual en segundo plano. Solo admin (POST)."""
    if not es_admin(request.user):
        return JsonResponse({'error': 'sin permiso'}, status=403)
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    integ = get_object_or_404(Integracion, id=integracion_id, proveedor='shalom')
    _lanzar_shalom(['--integracion', str(integ.id), '--manual'])
    return JsonResponse({'ok': True, 'mensaje': 'Actualización iniciada en segundo plano.'})


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
