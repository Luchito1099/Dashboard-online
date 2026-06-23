# integraciones/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseNotAllowed

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
    integ.activo = request.POST.get('activo') == 'on'

    # Credenciales: solo se actualizan si el campo viene con contenido nuevo
    for campo in ('token', 'api_key', 'api_secret'):
        nuevo = request.POST.get(campo, '').strip()
        if nuevo:
            setattr(integ, campo, nuevo)

    integ.save()
    messages.success(request, f'Integración «{integ.nombre}» actualizada.')
    return redirect(reverse_lista() + f'#integ-{integ.id}')


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


def reverse_lista():
    """URL de la lista (helper para concatenar anclas #integ-<id>)."""
    from django.urls import reverse
    return reverse('integraciones:lista')
