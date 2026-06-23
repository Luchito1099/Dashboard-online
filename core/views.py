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
from .models import Perfil, ConfiguracionSistema
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

    context = {
        'cap_total': total,
        'cap_done': done,
        'ped_hoy_c': glob['hoy_c'] or 0,
        'ped_hoy_m': glob['hoy_m'] or 0,
        'ped_tot_c': glob['tot_c'] or 0,
        'ped_tot_m': glob['tot_m'] or 0,
        'ped_moneda': moneda,
        'ped_fuentes': fuentes,
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
            config.save()
            messages.success(request, 'Configuración guardada.')

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

    context = {
        'usuarios_info': usuarios_info,
        'config': config,
        'roles': Perfil.ROL_CHOICES,
    }
    return render(request, 'core/configuracion.html', context)


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
