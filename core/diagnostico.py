# core/diagnostico.py
"""Diagnóstico de *salud de datos* del matching de productos.

Calidad de datos, NO operación: mide qué tan bien están casados los datos que ya
entraron (pedidos ↔ catálogo, anuncios ↔ producto), independientemente de si la
sincronización/scraper corrió (eso son los Logs de Shalom/sync).

`generar_diagnostico()` devuelve un dict serializable a JSON que consumen tanto el
management command `diagnostico_matching` como la vista «Salud de Datos». Así la lógica
vive en un solo lugar."""
from decimal import Decimal
from datetime import timedelta

from django.db.models import Count, Sum, F, DecimalField
from django.utils import timezone


def _sum_importe():
    """Sum(precio * cantidad) como expresión agregable. Nueva instancia por llamada
    (no reutilizar el mismo objeto entre queries)."""
    return Sum(F('precio') * F('cantidad'),
               output_field=DecimalField(max_digits=16, decimal_places=2))


def _f(x):
    """Decimal/None → float redondeado (para JSON)."""
    if x is None:
        return 0.0
    return round(float(x), 2)


def items_sin_match():
    """(a) PedidoItem sin producto, agrupados por (nombre, variante), ordenados por
    ocurrencias desc, con suma de importe (precio*cantidad) afectado."""
    from integraciones.models import PedidoItem

    qs = (PedidoItem.objects.filter(producto__isnull=True)
          .exclude(nombre='')
          .values('nombre', 'variante')
          .annotate(ocurrencias=Count('id'),
                    unidades=Sum('cantidad'),   # no llamar 'cantidad': sombrearía el campo en _sum_importe
                    monto=_sum_importe())
          .order_by('-ocurrencias', '-monto'))
    grupos = [{
        'nombre': r['nombre'],
        'variante': r['variante'] or '',
        'ocurrencias': r['ocurrencias'],
        'cantidad': r['unidades'] or 0,
        'monto': _f(r['monto']),
    } for r in qs]

    tot = PedidoItem.objects.filter(producto__isnull=True).aggregate(
        n=Count('id'), monto=_sum_importe())
    return {
        'total_items': tot['n'] or 0,
        'total_monto': _f(tot['monto']),
        'grupos': grupos,
    }


def alias_problemas():
    """(b) ProductoAlias problemáticos:
    - duplicados: mismo nombre_externo en >1 alias (típicamente distinta integración).
      Se marca 'conflicto' si apuntan a productos distintos (mismo nombre, distinto destino).
    - huérfanos: alias cuyo nombre_externo NO aparece en ningún PedidoItem (nunca aplicó,
      probable resto de una fuente vieja o typo)."""
    from productos.models import ProductoAlias
    from integraciones.models import PedidoItem

    # -- duplicados por nombre_externo --
    repetidos = (ProductoAlias.objects.values('nombre_externo')
                 .annotate(n=Count('id'))
                 .filter(n__gt=1)
                 .values_list('nombre_externo', flat=True))
    duplicados = []
    for nombre in repetidos:
        filas = (ProductoAlias.objects.filter(nombre_externo=nombre)
                 .select_related('producto', 'integracion'))
        productos_ids = {a.producto_id for a in filas}
        duplicados.append({
            'nombre_externo': nombre,
            'conflicto': len(productos_ids) > 1,   # apunta a productos distintos
            'entradas': [{
                'alias_id': a.id,
                'integracion': a.integracion.nombre if a.integracion else '(global)',
                'producto': a.producto.nombre,
                'producto_id': a.producto_id,
                'sku_externo': a.sku_externo,
            } for a in filas],
        })

    # -- huérfanos: nombre_externo sin uso en PedidoItem (comparación case-insensitive) --
    usados = {n.lower() for n in
              PedidoItem.objects.exclude(nombre='').values_list('nombre', flat=True).distinct()}
    huerfanos = []
    for a in ProductoAlias.objects.select_related('producto').all():
        if a.nombre_externo.lower() not in usados:
            huerfanos.append({
                'alias_id': a.id,
                'nombre_externo': a.nombre_externo,
                'producto': a.producto.nombre,
            })

    return {'duplicados': duplicados, 'huerfanos': huerfanos}


def pedidos_por_fecha(dias=30):
    """(c) Conteo de Pedido por integración vs fecha (últimos `dias`), detectando huecos
    de sincronización (días sin ningún pedido entre el primero y el último con datos)."""
    from integraciones.models import Pedido, Integracion

    desde = timezone.localdate() - timedelta(days=dias)
    salida = []
    fuentes = Integracion.objects.filter(categoria=Integracion.CATEGORIA_FUENTE).order_by('nombre')
    for integ in fuentes:
        filas = (Pedido.objects
                 .filter(integracion=integ, fecha_pedido__date__gte=desde)
                 .values('fecha_pedido__date')
                 .annotate(n=Count('id'))
                 .order_by('fecha_pedido__date'))
        por_dia = {r['fecha_pedido__date']: r['n'] for r in filas if r['fecha_pedido__date']}
        dias_lista = [{'fecha': f.isoformat(), 'n': n} for f, n in sorted(por_dia.items())]

        huecos = []
        if len(por_dia) >= 2:
            fechas = sorted(por_dia)
            cur = fechas[0]
            while cur <= fechas[-1]:
                if cur not in por_dia:
                    huecos.append(cur.isoformat())
                cur += timedelta(days=1)

        salida.append({
            'integracion_id': integ.id,
            'integracion': integ.nombre,
            'total': sum(por_dia.values()),
            'dias': dias_lista,
            'huecos': huecos,
        })
    return salida


def campanas_sin_match():
    """(d) CampanaMeta activa (incluida en extracción) sin MatchProductoAnuncio: anuncios
    que corren pero no están asociados a ningún producto del catálogo."""
    from anuncios.models import CampanaMeta

    qs = (CampanaMeta.objects
          .filter(incluir_en_extraccion=True, match__isnull=True)
          .select_related('cuenta')
          .order_by('campaign_name', 'ad_name'))
    return [{
        'id': c.id,
        'ad_name': c.ad_name or c.ad_id,
        'campaign_name': c.campaign_name,
        'cuenta': c.cuenta.nombre,
    } for c in qs]


def resumen_por_integracion():
    """% de PedidoItem matcheados vs sin matchear, por integración (para las cards)."""
    from integraciones.models import PedidoItem
    from django.db.models import Q

    filas = (PedidoItem.objects
             .values('pedido__integracion', 'pedido__integracion__nombre')
             .annotate(total=Count('id'),
                       con=Count('id', filter=Q(producto__isnull=False)))
             .order_by('pedido__integracion__nombre'))
    salida = []
    for r in filas:
        total = r['total'] or 0
        con = r['con'] or 0
        sin = total - con
        salida.append({
            'integracion_id': r['pedido__integracion'],
            'integracion': r['pedido__integracion__nombre'] or '(sin integración)',
            'total': total,
            'matcheados': con,
            'sin_match': sin,
            'pct_match': round(con * 100.0 / total, 1) if total else 0.0,
        })
    return salida


def generar_diagnostico(dias=30):
    """Ejecuta las cuatro secciones + el resumen y devuelve un dict serializable."""
    a = items_sin_match()
    return {
        'generado': timezone.now().isoformat(),
        'items_sin_match': a,
        'alias_problemas': alias_problemas(),
        'pedidos_por_fecha': pedidos_por_fecha(dias=dias),
        'campanas_sin_match': campanas_sin_match(),
        'resumen_por_integracion': resumen_por_integracion(),
    }


def guardar_snapshot(data, usuario=None):
    """Persiste un ReporteMatching a partir del dict de generar_diagnostico()."""
    from .models import ReporteMatching
    a = data.get('items_sin_match', {})
    return ReporteMatching.objects.create(
        total_items_sin_match=a.get('total_items', 0),
        total_monto_afectado=Decimal(str(a.get('total_monto', 0))),
        detalle=data,
        generado_por=usuario if (usuario and getattr(usuario, 'is_authenticated', False)) else None,
    )
