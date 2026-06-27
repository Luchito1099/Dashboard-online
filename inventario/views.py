# inventario/views.py
"""Inventario (solo admin): stock por almacén, planificador de reposición y CRUD de
almacenes/config de reposición."""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseNotAllowed, JsonResponse
from django.db.models import Sum

from capacitacion.views import es_admin
from productos.models import Producto
from integraciones.models import Integracion
from . import services
from .models import Almacen, StockProducto, MovimientoStock, ConfigReposicion


def _solo_admin(request):
    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos para ver el inventario.')
        return False
    return True


@login_required
def inventario(request):
    """Matriz producto × almacén con totales y ajuste manual inline."""
    if not _solo_admin(request):
        return redirect('core:home')

    almacenes = list(Almacen.objects.filter(activo=True))
    productos = list(Producto.objects.filter(activo=True)
                     .prefetch_related('variantes'))

    # Mapa (producto_id, variante_id|None, almacen_id) → cantidad
    stock_map = {(s.producto_id, s.variante_id, s.almacen_id): s.cantidad
                 for s in StockProducto.objects.all()}

    def _celdas(pid, vid):
        return [{'almacen': a, 'cantidad': stock_map.get((pid, vid, a.id), 0)} for a in almacenes]

    filas = []
    for p in productos:
        variantes = [v for v in p.variantes.all() if v.activo]
        # Total del producto = todo su stock (con o sin variantes)
        total_prod = sum(c for (pid, vid, aid), c in stock_map.items() if pid == p.id)
        if variantes:
            filas.append({'tipo': 'grupo', 'producto': p, 'total': total_prod})
            for v in variantes:
                celdas = _celdas(p.id, v.id)
                filas.append({'tipo': 'variante', 'producto': p, 'variante': v,
                              'celdas': celdas, 'total': sum(c['cantidad'] for c in celdas)})
        else:
            celdas = _celdas(p.id, None)
            filas.append({'tipo': 'simple', 'producto': p,
                          'celdas': celdas, 'total': sum(c['cantidad'] for c in celdas)})

    context = {
        'almacenes': almacenes,
        'filas': filas,
        'sin_almacenes': not almacenes,
    }
    return render(request, 'inventario/inventario.html', context)


@login_required
def ajustar_stock(request):
    """Fija el stock de un producto en un almacén a un valor exacto (registra el delta). POST."""
    if not es_admin(request.user):
        return redirect('core:home')
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    producto = get_object_or_404(Producto, id=request.POST.get('producto_id'))
    almacen = get_object_or_404(Almacen, id=request.POST.get('almacen_id'))
    # Variante opcional (color/talla)
    variante = None
    vid = request.POST.get('variante_id') or ''
    if vid.isdigit():
        from productos.models import VarianteProducto
        variante = VarianteProducto.objects.filter(id=vid, producto=producto).first()
    try:
        nuevo = int(request.POST.get('cantidad', '0') or 0)
    except ValueError:
        nuevo = 0

    # Ajuste manual = fija un valor ABSOLUTO (no suma delta). Así dos guardados casi
    # simultáneos (Enter) convergen al mismo valor y no se duplica.
    nuevo, actual = services.fijar_stock(producto, almacen, nuevo, variante=variante,
                                         usuario=request.user)
    if actual != nuevo:
        messages.success(request, f'Stock de «{producto.nombre}» en {almacen.nombre}: {actual} → {nuevo}.')

    # Guardado fluido (AJAX): devuelve el nuevo total del producto, sin recargar
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'ok': True, 'cantidad': nuevo, 'total': services.stock_total(producto)})
    return redirect('inventario:inventario')


@login_required
def reposicion(request):
    """Planificador: cuándo y cuánto comprar según velocidad de venta y lead time."""
    if not _solo_admin(request):
        return redirect('core:home')

    try:
        dias = int(request.GET.get('dias', '30') or 30)
    except ValueError:
        dias = 30
    dias = max(7, min(dias, 180))

    filas = services.plan_reposicion(ventana=dias)
    # Productos sin configuración de reposición (para invitar a configurarlos)
    con_config = set(ConfigReposicion.objects.values_list('producto_id', flat=True))
    sin_config = Producto.objects.filter(activo=True).exclude(id__in=con_config)

    context = {
        'filas': filas,
        'dias': dias,
        'sin_config': sin_config,
        'urgentes': sum(1 for f in filas if f['comprar_ya']),
    }
    return render(request, 'inventario/reposicion.html', context)


@login_required
def guardar_config(request):
    """Crea/actualiza la configuración de reposición de un producto. POST."""
    if not es_admin(request.user):
        return redirect('core:home')
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    producto = get_object_or_404(Producto, id=request.POST.get('producto_id'))

    def _int(name, default):
        try:
            return max(0, int(request.POST.get(name, default) or default))
        except ValueError:
            return default

    ConfigReposicion.objects.update_or_create(
        producto=producto,
        defaults={
            'dias_entrega': _int('dias_entrega', 30),
            'dias_seguridad': _int('dias_seguridad', 7),
            'dias_cobertura': _int('dias_cobertura', 60),
            'activo': request.POST.get('activo', 'on') == 'on',
        })
    messages.success(request, f'Reposición de «{producto.nombre}» guardada.')
    return redirect(f"{request.META.get('HTTP_REFERER', '')}" or 'inventario:reposicion')


@login_required
def almacenes(request):
    """CRUD de almacenes."""
    if not _solo_admin(request):
        return redirect('core:home')

    if request.method == 'POST':
        accion = request.POST.get('accion')
        if accion == 'crear':
            nombre = request.POST.get('nombre', '').strip()
            if nombre:
                integ_id = request.POST.get('integracion') or None
                Almacen.objects.create(
                    nombre=nombre,
                    integracion_id=integ_id if (integ_id and integ_id.isdigit()) else None,
                    es_principal=request.POST.get('es_principal') == 'on',
                    orden=Almacen.objects.count())
                messages.success(request, f'Almacén «{nombre}» creado.')
            else:
                messages.error(request, 'El almacén necesita un nombre.')
        elif accion == 'editar':
            a = get_object_or_404(Almacen, id=request.POST.get('almacen_id'))
            a.nombre = request.POST.get('nombre', a.nombre).strip() or a.nombre
            integ_id = request.POST.get('integracion') or None
            a.integracion_id = integ_id if (integ_id and integ_id.isdigit()) else None
            a.es_principal = request.POST.get('es_principal') == 'on'
            a.activo = request.POST.get('activo') == 'on'
            a.save()
            messages.success(request, f'Almacén «{a.nombre}» actualizado.')
        elif accion == 'eliminar':
            a = get_object_or_404(Almacen, id=request.POST.get('almacen_id'))
            nombre = a.nombre
            a.delete()
            messages.success(request, f'Almacén «{nombre}» eliminado.')
        return redirect('inventario:almacenes')

    context = {
        'almacenes': Almacen.objects.all(),
        'fuentes': Integracion.objects.all(),
    }
    return render(request, 'inventario/almacenes.html', context)
