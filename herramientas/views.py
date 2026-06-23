# herramientas/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseNotAllowed

# Reutilizamos el helper de permisos existente (no lo duplicamos)
from capacitacion.views import es_admin
from .models import HerramientaExterna


@login_required
def lista(request):
    """Grid de herramientas externas (acceso configurable para el vendedor)."""
    from core.permisos import puede_ver, destino_vendedor
    if not puede_ver(request.user, 'vendedor_puede_ver_herramientas'):
        messages.error(request, 'No tienes permisos para ver las herramientas.')
        return redirect(destino_vendedor(request.user))

    herramientas = HerramientaExterna.objects.filter(activo=True)
    # Agrupamos por categoría para mostrarlas en secciones
    categorias = sorted({h.categoria for h in herramientas if h.categoria})
    context = {
        'herramientas': herramientas,
        'categorias': categorias,
        'puede_editar': es_admin(request.user),
    }
    return render(request, 'herramientas/lista.html', context)


# ───────────────────────── Administración (solo admin) ─────────────────────────

@login_required
def admin_herramientas(request):
    """Lista editable de herramientas. Solo admin."""
    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos para administrar herramientas.')
        return redirect('herramientas:lista')

    herramientas = HerramientaExterna.objects.all()
    return render(request, 'herramientas/admin.html', {'herramientas': herramientas})


@login_required
def crear_herramienta(request):
    """Crea una herramienta vacía para completarla. Solo admin (POST)."""
    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos para crear herramientas.')
        return redirect('herramientas:lista')
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    HerramientaExterna.objects.create(
        nombre='Nueva herramienta', url='https://', orden=HerramientaExterna.objects.count() + 1
    )
    messages.success(request, 'Herramienta creada. Edítala abajo.')
    return redirect('herramientas:admin')


@login_required
def editar_herramienta(request, herramienta_id):
    """Guarda los cambios de una herramienta. Solo admin (POST)."""
    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos para editar herramientas.')
        return redirect('herramientas:lista')
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    h = get_object_or_404(HerramientaExterna, id=herramienta_id)
    h.nombre = request.POST.get('nombre', h.nombre).strip()
    h.descripcion = request.POST.get('descripcion', h.descripcion).strip()
    h.url = request.POST.get('url', h.url).strip()
    h.icono = request.POST.get('icono', h.icono).strip()
    h.categoria = request.POST.get('categoria', h.categoria).strip()
    h.activo = request.POST.get('activo') == 'on'
    h.save()
    messages.success(request, f'Herramienta «{h.nombre}» actualizada.')
    return redirect('herramientas:admin')


@login_required
def eliminar_herramienta(request, herramienta_id):
    """Elimina una herramienta. Solo admin (POST)."""
    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos para eliminar herramientas.')
        return redirect('herramientas:lista')
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    h = get_object_or_404(HerramientaExterna, id=herramienta_id)
    nombre = h.nombre
    h.delete()
    messages.success(request, f'Herramienta «{nombre}» eliminada.')
    return redirect('herramientas:admin')
