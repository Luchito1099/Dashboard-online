# productos/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseNotAllowed

import difflib

from django.db.models import Count
from django.http import JsonResponse

# Reutilizamos el helper de permisos ya existente (no lo duplicamos)
from capacitacion.views import es_admin
from core.models import ConfiguracionSistema
from .models import (Producto, ObjecionProducto, LinkProducto, MediaProducto, ProductoAlias,
                     AtributoProducto, ValorAtributo, VarianteProducto, generar_variantes)


# ───────────────────────── Helpers ─────────────────────────

def _vendedor_puede_ver(user):
    """El vendedor solo ve productos si la configuración lo permite. El admin siempre."""
    if es_admin(user):
        return True
    config = ConfiguracionSistema.get_solo()
    return config.vendedor_puede_ver_productos


def _producto_a_dict(p):
    """Serializa un producto para el JS del catálogo (panel de detalle, búsqueda)."""
    return {
        'id': p.id,
        'nombre': p.nombre,
        'sku': p.sku,
        'categoria': p.categoria,
        'precio': float(p.precio),
        'precio_oferta': float(p.precio_oferta) if p.precio_oferta is not None else None,
        'en_oferta': p.tiene_oferta,
        'precio_mostrar': float(p.precio_mostrar),
        'descripcion': p.descripcion,
        'caracteristicas': p.caracteristicas or [],
        'imagen_url': p.imagen_url,
        'video_url': p.video_url,
        'link_pago': p.link_pago,
        'imagenes': [img.url for img in p.imagenes.all()],
        # Múltiples enlaces web del producto
        'links': [{'titulo': l.titulo, 'url': l.url} for l in p.links.all()],
        # Material compartible (imágenes y videos)
        'medios': [{'tipo': m.tipo, 'url': m.url, 'titulo': m.titulo} for m in p.medios.all()],
    }


# ───────────────────────── Catálogo ─────────────────────────

@login_required
def catalogo(request, producto_id=None):
    """Grid de productos con buscador local y panel de detalle (JS)."""
    if not _vendedor_puede_ver(request.user):
        messages.error(request, 'No tienes permisos para ver el catálogo de productos.')
        return redirect('core:home')

    productos = Producto.objects.filter(activo=True).prefetch_related('imagenes', 'links', 'medios')
    productos_data = [_producto_a_dict(p) for p in productos]
    # Categorías únicas para el filtro
    categorias = sorted({p.categoria for p in productos if p.categoria})

    context = {
        'productos': productos,
        'productos_data': productos_data,
        'categorias': categorias,
        'puede_editar': es_admin(request.user),
        'producto_inicial': producto_id,  # si viene, el JS abre ese detalle al cargar
    }
    return render(request, 'productos/catalogo.html', context)


@login_required
def detalle(request, producto_id):
    """Ficha completa = catálogo con el panel de detalle abierto en ese producto."""
    # get_object_or_404 valida que exista antes de abrir el catálogo
    get_object_or_404(Producto, id=producto_id, activo=True)
    return catalogo(request, producto_id=producto_id)


@login_required
def ficha_rapida(request, producto_id):
    """Vista compacta de una sola pantalla para usar durante una llamada."""
    if not _vendedor_puede_ver(request.user):
        messages.error(request, 'No tienes permisos para ver productos.')
        return redirect('core:home')

    producto = get_object_or_404(
        Producto.objects.prefetch_related('objeciones', 'links', 'medios'), id=producto_id
    )
    return render(request, 'productos/ficha_rapida.html', {'producto': producto})


# ───────────────────────── Administración (solo admin) ─────────────────────────

@login_required
def admin_productos(request):
    """Lista editable de productos. Solo admin."""
    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos para administrar productos.')
        return redirect('productos:catalogo')

    productos = Producto.objects.all().prefetch_related('objeciones', 'links', 'medios')
    return render(request, 'productos/admin.html', {'productos': productos})


@login_required
def crear_producto(request):
    """Crea un producto vacío y redirige al admin para completarlo. Solo admin (POST)."""
    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos para crear productos.')
        return redirect('productos:catalogo')
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    Producto.objects.create(nombre='Producto nuevo', orden=Producto.objects.count() + 1)
    messages.success(request, 'Producto nuevo creado. Edítalo abajo.')
    return redirect('productos:admin')


@login_required
def editar_producto(request, producto_id):
    """Guarda los cambios de un producto desde el panel admin. Solo admin (POST)."""
    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos para editar productos.')
        return redirect('productos:catalogo')
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    producto = get_object_or_404(Producto, id=producto_id)

    # Campos de texto
    producto.nombre = request.POST.get('nombre', producto.nombre).strip()
    producto.sku = request.POST.get('sku', producto.sku).strip()
    producto.categoria = request.POST.get('categoria', producto.categoria).strip()
    producto.descripcion = request.POST.get('descripcion', producto.descripcion).strip()
    producto.imagen_url = request.POST.get('imagen_url', producto.imagen_url).strip()
    producto.video_url = request.POST.get('video_url', producto.video_url).strip()
    producto.link_pago = request.POST.get('link_pago', producto.link_pago).strip()

    # Precios (con conversión segura)
    producto.precio = _a_decimal(request.POST.get('precio'), producto.precio)
    producto.precio_oferta = _a_decimal(request.POST.get('precio_oferta'), None, permitir_nulo=True)
    producto.en_oferta = request.POST.get('en_oferta') == 'on'

    # Características: una por línea
    caract_raw = request.POST.get('caracteristicas', '')
    producto.caracteristicas = [c.strip() for c in caract_raw.splitlines() if c.strip()]

    producto.save()

    # Objeciones: reemplazamos todas con las del textarea (formato "objecion|respuesta" por línea)
    objeciones_raw = request.POST.get('objeciones', '')
    producto.objeciones.all().delete()
    for i, linea in enumerate(objeciones_raw.splitlines()):
        linea = linea.strip()
        if not linea or '|' not in linea:
            continue
        obj, resp = linea.split('|', 1)
        ObjecionProducto.objects.create(
            producto=producto, objecion=obj.strip(), respuesta=resp.strip(), orden=i
        )

    # Links web: reemplazamos todos (formato "titulo|url" por línea)
    links_raw = request.POST.get('links', '')
    producto.links.all().delete()
    for i, linea in enumerate(links_raw.splitlines()):
        linea = linea.strip()
        if not linea or '|' not in linea:
            continue
        titulo, url = linea.split('|', 1)
        if url.strip():
            LinkProducto.objects.create(
                producto=producto, titulo=titulo.strip(), url=url.strip(), orden=i
            )

    # Medios compartibles: reemplazamos todos (formato "tipo|url|titulo" por línea; tipo=imagen|video)
    medios_raw = request.POST.get('medios', '')
    producto.medios.all().delete()
    for i, linea in enumerate(medios_raw.splitlines()):
        partes = [x.strip() for x in linea.split('|')]
        if len(partes) < 2 or not partes[1]:
            continue
        tipo = partes[0].lower()
        if tipo not in ('imagen', 'video'):
            tipo = 'imagen'
        titulo = partes[2] if len(partes) >= 3 else ''
        MediaProducto.objects.create(
            producto=producto, tipo=tipo, url=partes[1], titulo=titulo, orden=i
        )

    messages.success(request, f'Producto «{producto.nombre}» actualizado.')
    return redirect('productos:admin')


@login_required
def eliminar_producto(request, producto_id):
    """Elimina un producto. Solo admin (POST)."""
    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos para eliminar productos.')
        return redirect('productos:catalogo')
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    producto = get_object_or_404(Producto, id=producto_id)
    nombre = producto.nombre
    producto.delete()
    messages.success(request, f'Producto «{nombre}» eliminado.')
    return redirect('productos:admin')


# ───────────────────────── Reconocer productos de pedidos (matching) ─────────────────────────

@login_required
def reconocer_productos(request):
    """Lista los nombres de producto que llegan en los pedidos (PedidoItem) y que aún
    NO están vinculados al catálogo, con sugerencias para asignarlos. Al asignar, crea
    un ProductoAlias y enlaza todos los pedidos con ese nombre. Solo admin."""
    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos para reconocer productos.')
        return redirect('productos:catalogo')

    from integraciones.models import PedidoItem
    nombres = (PedidoItem.objects.filter(producto__isnull=True).exclude(nombre='')
               .values('nombre').annotate(n=Count('id')).order_by('-n'))

    productos = list(Producto.objects.all())
    items = [{'nombre': r['nombre'], 'n': r['n']} for r in nombres]

    # Aliases ya vinculados (para la sección "Ya vinculados")
    aliases = (ProductoAlias.objects.select_related('producto', 'variante')
               .order_by('nombre_externo'))

    # Variantes activas por producto, para el selector dependiente color/talla.
    import json
    variantes_por_producto = {}
    for v in VarianteProducto.objects.filter(activo=True).order_by('producto_id', 'orden'):
        variantes_por_producto.setdefault(v.producto_id, []).append({'id': v.id, 'nombre': v.nombre})

    context = {
        'items': items,
        'productos': productos,
        'total': len(items),
        'vinculados': PedidoItem.objects.filter(producto__isnull=False).count(),
        'aliases': aliases,
        'variantes_json': json.dumps(variantes_por_producto),
    }
    return render(request, 'productos/reconocer.html', context)


@login_required
def vincular_producto(request):
    """Asocia un nombre de producto de pedidos a un Producto del catálogo: crea el alias
    y enlaza todos los PedidoItem con ese nombre. Solo admin (POST)."""
    if not es_admin(request.user):
        return JsonResponse({'error': 'sin permiso'}, status=403)
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    from integraciones.models import PedidoItem
    nombre = request.POST.get('nombre', '').strip()
    producto = get_object_or_404(Producto, id=request.POST.get('producto_id'))
    if not nombre:
        return redirect('productos:reconocer')

    # Variante opcional (color/talla): debe pertenecer al producto elegido.
    variante = None
    variante_id = request.POST.get('variante_id', '').strip()
    if variante_id:
        variante = VarianteProducto.objects.filter(id=variante_id, producto=producto).first()

    # Alias global (aplica a cualquier fuente) para futuras sincronizaciones
    ProductoAlias.objects.update_or_create(
        integracion=None, nombre_externo=nombre,
        defaults={'producto': producto, 'variante': variante})
    # Vincular los pedidos existentes con ese nombre. Si se eligió variante y la línea no
    # trae texto de variante, se rellena con el nombre de la variante para que quede visible.
    items = PedidoItem.objects.filter(nombre__iexact=nombre, producto__isnull=True)
    n = items.count()
    items.update(producto=producto)
    if variante:
        items.model.objects.filter(nombre__iexact=nombre, producto=producto, variante='').update(
            variante=variante.nombre)
    detalle = f' · {variante.nombre}' if variante else ''
    messages.success(request, f'«{nombre}» vinculado a «{producto.nombre}»{detalle} ({n} línea(s) de pedido).')
    return redirect('productos:reconocer')


@login_required
def editar_atributos(request, producto_id):
    """Define los atributos (Color, Talla…) de un producto desde un textarea y regenera
    las variantes (combinaciones). Formato por línea: «Atributo: val1, val2». Solo admin (POST)."""
    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos.')
        return redirect('productos:catalogo')
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    producto = get_object_or_404(Producto, id=producto_id)
    producto.atributos.all().delete()   # borra atributos+valores; las variantes se regeneran
    for i, linea in enumerate(request.POST.get('atributos', '').splitlines()):
        linea = linea.strip()
        if not linea or ':' not in linea:
            continue
        nombre, valores = linea.split(':', 1)
        nombre = nombre.strip()
        vals = [v.strip() for v in valores.split(',') if v.strip()]
        if not nombre or not vals:
            continue
        attr = AtributoProducto.objects.create(producto=producto, nombre=nombre, orden=i)
        for j, val in enumerate(vals):
            ValorAtributo.objects.create(atributo=attr, valor=val, orden=j)

    n = generar_variantes(producto)
    messages.success(request, f'Variantes de «{producto.nombre}»: {n} combinación(es).')
    from django.urls import reverse
    return redirect(reverse('productos:admin') + f'#producto-{producto.id}')


@login_required
def quitar_alias(request):
    """Elimina un alias (desvincula nombre de pedido del catálogo). Solo admin (POST)."""
    if not es_admin(request.user):
        return JsonResponse({'error': 'sin permiso'}, status=403)
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    from integraciones.models import PedidoItem
    nombre = request.POST.get('nombre', '').strip()
    if nombre:
        ProductoAlias.objects.filter(nombre_externo__iexact=nombre, integracion=None).delete()
        PedidoItem.objects.filter(nombre__iexact=nombre).update(producto=None)
        messages.success(request, f'Vínculo «{nombre}» eliminado.')
    return redirect('productos:reconocer')


# ───────────────────────── Utilidades internas ─────────────────────────

def _a_decimal(valor, por_defecto, permitir_nulo=False):
    """Convierte un string a número; si está vacío o falla, devuelve el valor por defecto."""
    if valor is None or valor.strip() == '':
        return None if permitir_nulo else por_defecto
    try:
        return round(float(valor), 2)
    except (ValueError, TypeError):
        return por_defecto
