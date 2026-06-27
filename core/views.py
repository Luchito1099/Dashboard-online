# core/views.py
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone

from capacitacion.models import Tarea, ProgresoTarea
from capacitacion.views import es_admin  # reutilizamos el helper de permisos
from .models import Perfil, ConfiguracionSistema, MetaVendedor, ConexionIA, HerramientaIA
from .permisos import puede_ver, destino_vendedor


@login_required
def home(request):
    """Inicio: KPIs de pedidos (hoy/acumulado) + resumen del progreso de capacitación."""
    if not puede_ver(request.user, 'vendedor_puede_ver_inicio'):
        return redirect(destino_vendedor(request.user))

    from django.db.models import Sum, Count, Q
    from integraciones.models import Pedido, Integracion

    hoy = timezone.localdate()

    total = Tarea.objects.filter(activo=True).count()
    done = ProgresoTarea.objects.filter(
        usuario=request.user, fecha=hoy, completada=True
    ).count()

    # ── Pedidos: totales globales (todas las fuentes) ──
    pedidos = Pedido.objects.all()
    glob = pedidos.aggregate(
        tot_c=Count('id'), tot_m=Sum('total'),
        hoy_c=Count('id', filter=Q(fecha_pedido__date=hoy)),
        hoy_m=Sum('total', filter=Q(fecha_pedido__date=hoy)),
    )
    moneda = pedidos.values_list('moneda', flat=True).first() or 'S/'

    # ── Desglose por fuente de pedidos ──
    fuentes = Integracion.objects.filter(
        categoria=Integracion.CATEGORIA_FUENTE
    ).annotate(
        d_tot_c=Count('pedidos'),
        d_tot_m=Sum('pedidos__total'),
        d_hoy_c=Count('pedidos', filter=Q(pedidos__fecha_pedido__date=hoy)),
        d_hoy_m=Sum('pedidos__total', filter=Q(pedidos__fecha_pedido__date=hoy)),
    )

    # Campañas y proyectos para los filtros de los gráficos de publicidad (solo si puede ver ads).
    # Las campañas se agrupan: primero las INCLUIDAS en el análisis (Ajustes), luego las otras.
    from .permisos import puede_ver_ads
    campanas_incluidas, campanas_otras, proyectos_ads = [], [], []
    if puede_ver_ads(request.user):
        from anuncios.models import CampanaMeta
        from django.db.models import Max, Count
        # Nota: Max() sobre el booleano incluir_en_extraccion no existe en PostgreSQL;
        # usamos Count con filtro (cross-DB) → "incluida" = al menos un anuncio incluido.
        camps = (CampanaMeta.objects.values('campaign_id')
                 .annotate(nombre=Max('campaign_name'), proyecto=Max('proyecto'),
                           n_incluidos=Count('id', filter=Q(incluir_en_extraccion=True)))
                 .order_by('nombre'))
        for c in camps:
            destino = campanas_incluidas if c['n_incluidos'] else campanas_otras
            destino.append({'campaign_id': c['campaign_id'],
                            'nombre': c['nombre'] or '(sin campaña)',
                            'proyecto': c['proyecto'] or ''})
        proyectos_ads = sorted({c['proyecto'] for c in camps if c['proyecto']})

    context = {
        'cap_total': total,
        'cap_done': done,
        'ped_hoy_c': glob['hoy_c'] or 0,
        'ped_hoy_m': glob['hoy_m'] or 0,
        'ped_tot_c': glob['tot_c'] or 0,
        'ped_tot_m': glob['tot_m'] or 0,
        'ped_moneda': moneda,
        'ped_fuentes': fuentes,
        'campanas_incluidas': campanas_incluidas,
        'campanas_otras': campanas_otras,
        'proyectos_ads': proyectos_ads,
    }
    return render(request, 'core/home.html', context)


def login_view(request):
    """Autenticación estándar de Django. Si ya está logueado, va al inicio."""
    if request.user.is_authenticated:
        return redirect('core:home')

    error = None
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect('core:home')
        error = 'Usuario o contraseña incorrectos'

    return render(request, 'registration/login.html', {'error': error})


def logout_view(request):
    """Cierra la sesión y regresa al login."""
    logout(request)
    return redirect('core:login')


@login_required
def sin_acceso(request):
    """Página de respaldo cuando un vendedor no tiene ningún módulo habilitado."""
    return render(request, 'core/sin_acceso.html')


# ───────────────────────── Configuración (solo admin) ─────────────────────────

@login_required
def configuracion(request):
    """Gestión de usuarios y limitaciones por rol. Solo accesible para admin."""
    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos para acceder a la configuración.')
        return redirect('core:home')

    config = ConfiguracionSistema.get_solo()

    # ── Acciones POST ──
    if request.method == 'POST':
        accion = request.POST.get('accion')

        if accion == 'crear_usuario':
            _crear_usuario(request)

        elif accion == 'cambiar_rol':
            _cambiar_rol(request)

        elif accion == 'toggle_activo':
            _toggle_activo(request)

        elif accion == 'guardar_config':
            # Los checkboxes solo llegan si están marcados
            config.vendedor_puede_editar_videos = request.POST.get('vendedor_puede_editar_videos') == 'on'
            config.vendedor_puede_ver_productos = request.POST.get('vendedor_puede_ver_productos') == 'on'
            config.vendedor_puede_ver_inicio = request.POST.get('vendedor_puede_ver_inicio') == 'on'
            config.vendedor_puede_ver_capacitacion = request.POST.get('vendedor_puede_ver_capacitacion') == 'on'
            config.vendedor_puede_ver_herramientas = request.POST.get('vendedor_puede_ver_herramientas') == 'on'
            config.vendedor_puede_compartir = request.POST.get('vendedor_puede_compartir') == 'on'
            config.vendedor_puede_ver_pedidos = request.POST.get('vendedor_puede_ver_pedidos') == 'on'
            config.vendedor_puede_editar_pedidos = request.POST.get('vendedor_puede_editar_pedidos') == 'on'
            config.vendedor_puede_ver_seguimiento = request.POST.get('vendedor_puede_ver_seguimiento') == 'on'
            config.vendedor_puede_editar_seguimiento = request.POST.get('vendedor_puede_editar_seguimiento') == 'on'
            config.vendedor_puede_registrar_pedidos = request.POST.get('vendedor_puede_registrar_pedidos') == 'on'
            config.vendedor_puede_ver_avances = request.POST.get('vendedor_puede_ver_avances') == 'on'
            config.analista_puede_editar_seguimiento = request.POST.get('analista_puede_editar_seguimiento') == 'on'
            config.save()
            messages.success(request, 'Configuración guardada.')

        elif accion == 'guardar_metas':
            _guardar_metas(request)

        elif accion == 'guardar_ia':
            _guardar_ia(request)

        elif accion == 'eliminar_ia':
            _eliminar_ia(request)

        elif accion == 'probar_ia':
            _probar_ia(request)

        elif accion == 'guardar_herramienta_ia':
            _guardar_herramienta_ia(request)

        elif accion == 'crear_herramienta_ia':
            _crear_herramienta_ia(request)

        return redirect('core:configuracion')

    # ── GET: listamos usuarios con su perfil (creándolo si faltara) ──
    usuarios_info = []
    for u in User.objects.all().order_by('username'):
        perfil, _ = Perfil.objects.get_or_create(usuario=u)
        usuarios_info.append({
            'id': u.id,
            'username': u.username,
            'email': u.email,
            'rol': perfil.rol,
            'activo': perfil.activo,
            'es_superuser': u.is_superuser,
        })

    # ── Metas por vendedor (rol vendedor/admin o superuser) ──
    metas_info = []
    vendedores = (User.objects.filter(is_active=True)
                  .filter(Q(perfil__rol__in=['vendedor', 'admin']) | Q(is_superuser=True))
                  .order_by('username'))
    for v in vendedores:
        meta, _ = MetaVendedor.objects.get_or_create(usuario=v)
        metas_info.append({
            'id': v.id,
            'nombre': v.get_full_name() or v.username,
            'pedidos_dia': meta.pedidos_dia,
            'monto_dia': meta.monto_dia,
        })

    context = {
        'usuarios_info': usuarios_info,
        'config': config,
        'roles': Perfil.ROL_CHOICES,
        'metas_info': metas_info,
        'conexiones_ia': ConexionIA.objects.all(),
        'proveedores_ia': ConexionIA.PROVEEDOR_CHOICES,
        # Asegura que existan las herramientas cableadas y lista todas
        'herramientas_ia': (HerramientaIA.registrar_pedido(),
                            HerramientaIA.matching_pedidos(),
                            HerramientaIA.objects.all())[2],
    }
    return render(request, 'core/configuracion.html', context)


def _guardar_herramienta_ia(request):
    """Guarda el prompt, la conexión y el estado de una herramienta de IA."""
    h = HerramientaIA.objects.filter(id=request.POST.get('herramienta_id')).first()
    if not h:
        return
    h.prompt = request.POST.get('prompt', h.prompt)
    cid = request.POST.get('conexion', '')
    h.conexion_id = int(cid) if cid.isdigit() else None
    h.activa = request.POST.get('activa') == 'on'
    h.save()
    messages.success(request, f'Herramienta «{h.nombre}» guardada.')


def _crear_herramienta_ia(request):
    """Crea una herramienta de IA nueva (para usos futuros). Solo «registrar_pedido» está cableada."""
    from django.utils.text import slugify
    nombre = request.POST.get('nombre', '').strip()
    if not nombre:
        messages.error(request, 'La herramienta necesita un nombre.')
        return
    slug = slugify(request.POST.get('slug', '') or nombre)[:50]
    if HerramientaIA.objects.filter(slug=slug).exists():
        messages.error(request, f'Ya existe una herramienta con slug «{slug}».')
        return
    HerramientaIA.objects.create(slug=slug, nombre=nombre,
                                 prompt=request.POST.get('prompt', '').strip())
    messages.success(request, f'Herramienta «{nombre}» creada.')


def _guardar_ia(request):
    """Crea o actualiza una conexión de IA. La key solo se cambia si se escribe una nueva."""
    cid = request.POST.get('conexion_id', '').strip()
    nombre = request.POST.get('nombre', '').strip()
    if not nombre:
        messages.error(request, 'La conexión necesita un nombre.')
        return
    datos = {
        'nombre': nombre,
        'proveedor': request.POST.get('proveedor', ConexionIA.PROVEEDOR_ANTHROPIC),
        'modelo': request.POST.get('modelo', '').strip() or 'claude-haiku-4-5-20251001',
        'base_url': request.POST.get('base_url', '').strip(),
        'activa': request.POST.get('activa') == 'on',
    }
    key = request.POST.get('api_key', '').strip()
    if key:
        datos['api_key'] = key
    if cid.isdigit():
        ConexionIA.objects.filter(id=cid).update(**datos)
        messages.success(request, f'Conexión «{nombre}» actualizada.')
    else:
        if not key:
            messages.error(request, 'Para crear una conexión nueva indica la API key.')
            return
        ConexionIA.objects.create(**datos)
        messages.success(request, f'Conexión «{nombre}» creada.')


def _eliminar_ia(request):
    cid = request.POST.get('conexion_id', '')
    if str(cid).isdigit():
        ConexionIA.objects.filter(id=cid).delete()
        messages.success(request, 'Conexión eliminada.')


def _probar_ia(request):
    """Prueba la conexión contra el proveedor (llamada mínima)."""
    from . import ia
    cid = request.POST.get('conexion_id', '')
    conexion = ConexionIA.objects.filter(id=cid).first() if str(cid).isdigit() else None
    if not conexion:
        return
    ok, msg = ia.probar(conexion)
    (messages.success if ok else messages.error)(request, f'{conexion.nombre}: {msg}')


def _guardar_metas(request):
    """Guarda las metas diarias (pedidos y monto) de cada vendedor."""
    from decimal import Decimal, InvalidOperation
    ids = request.POST.getlist('meta_usuario')
    for uid in ids:
        if not str(uid).isdigit():
            continue
        try:
            usuario = User.objects.get(id=uid)
        except User.DoesNotExist:
            continue
        meta, _ = MetaVendedor.objects.get_or_create(usuario=usuario)
        crudo_ped = (request.POST.get(f'pedidos_dia_{uid}') or '0').strip()
        crudo_monto = (request.POST.get(f'monto_dia_{uid}') or '0').strip().replace(',', '.')
        try:
            meta.pedidos_dia = max(int(crudo_ped), 0) if crudo_ped else 0
        except ValueError:
            meta.pedidos_dia = 0
        try:
            v = Decimal(crudo_monto) if crudo_monto else Decimal('0')
            meta.monto_dia = v if v >= 0 else Decimal('0')
        except InvalidOperation:
            meta.monto_dia = Decimal('0')
        meta.save()
    messages.success(request, 'Metas de vendedores guardadas.')


def _crear_usuario(request):
    """Crea un usuario nuevo con el rol indicado (la señal crea su Perfil)."""
    username = request.POST.get('username', '').strip()
    password = request.POST.get('password', '').strip()
    rol = request.POST.get('rol', 'vendedor')

    if not username or not password:
        messages.error(request, 'Usuario y contraseña son obligatorios.')
        return
    if User.objects.filter(username=username).exists():
        messages.error(request, f'El usuario «{username}» ya existe.')
        return

    usuario = User.objects.create_user(username=username, password=password)
    # La señal post_save ya creó el Perfil; ajustamos el rol elegido
    perfil = usuario.perfil
    perfil.rol = rol
    perfil.save()
    messages.success(request, f'Usuario «{username}» creado con rol {rol}.')


def _cambiar_rol(request):
    """Cambia el rol (admin↔vendedor) de un usuario."""
    perfil = _get_perfil(request.POST.get('user_id'))
    if not perfil:
        return
    nuevo_rol = request.POST.get('rol')
    if nuevo_rol in dict(Perfil.ROL_CHOICES):
        perfil.rol = nuevo_rol
        perfil.save()
        messages.success(request, f'Rol de «{perfil.usuario.username}» cambiado a {nuevo_rol}.')


def _toggle_activo(request):
    """Activa/desactiva un usuario (perfil.activo + user.is_active)."""
    perfil = _get_perfil(request.POST.get('user_id'))
    if not perfil:
        return
    perfil.activo = not perfil.activo
    perfil.save()
    perfil.usuario.is_active = perfil.activo
    perfil.usuario.save()
    estado = 'activado' if perfil.activo else 'desactivado'
    messages.success(request, f'Usuario «{perfil.usuario.username}» {estado}.')


def _get_perfil(user_id):
    """Devuelve el Perfil de un usuario por id, o None (creándolo si faltara)."""
    try:
        usuario = User.objects.get(id=user_id)
    except (User.DoesNotExist, ValueError, TypeError):
        return None
    perfil, _ = Perfil.objects.get_or_create(usuario=usuario)
    return perfil


# ───────────────────────── Buscador global (topbar ⌘K) ─────────────────────────

@login_required
def api_buscar(request):
    """Busca tareas y productos por texto. Devuelve JSON {tareas:[...], productos:[...]}."""
    # Import local para evitar dependencia circular en el arranque
    from productos.models import Producto

    q = request.GET.get('q', '').strip()
    tareas, productos = [], []

    # Mínimo 2 caracteres para buscar
    if len(q) >= 2:
        for t in Tarea.objects.filter(activo=True, nombre__icontains=q)[:8]:
            tareas.append({'id': t.id, 'nombre': t.nombre, 'hora': t.hora, 'tipo': t.tipo})

        productos_qs = Producto.objects.filter(activo=True).filter(
            Q(nombre__icontains=q) | Q(categoria__icontains=q)
        )[:8]
        for p in productos_qs:
            productos.append({
                'id': p.id,
                'nombre': p.nombre,
                'categoria': p.categoria,
                'precio': float(p.precio_mostrar),
            })

    return JsonResponse({'tareas': tareas, 'productos': productos})
