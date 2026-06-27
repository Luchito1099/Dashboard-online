# inventario/services.py
"""Lógica de inventario: aplicar movimientos de stock, calcular la velocidad de venta
y el plan de reposición (cuándo y cuánto comprar), y descontar stock al entregar."""
import math
from datetime import timedelta

from django.db import transaction
from django.db.models import Sum, Q
from django.utils import timezone

from integraciones.models import Pedido, PedidoItem
from .models import Almacen, StockProducto, MovimientoStock, ConfigReposicion

# Demanda = pedidos comprometidos (confirmado + despachado + entregado)
ESTADOS_CONSUMO = [Pedido.ESTADO_CONFIRMADO, Pedido.ESTADO_DESPACHADO, Pedido.ESTADO_ENTREGADO]


# ───────────────────────── Movimientos de stock ─────────────────────────

@transaction.atomic
def aplicar_movimiento(producto, almacen, delta, motivo, variante=None,
                       pedido=None, usuario=None, nota=''):
    """Suma/resta `delta` al stock del producto (variante opcional) en el almacén y deja
    la traza. Atómico."""
    if delta == 0:
        return None
    sp, _ = (StockProducto.objects.select_for_update()
             .get_or_create(producto=producto, variante=variante, almacen=almacen))
    sp.cantidad = sp.cantidad + delta
    sp.save(update_fields=['cantidad', 'actualizado'])
    return MovimientoStock.objects.create(
        producto=producto, variante=variante, almacen=almacen, delta=delta, motivo=motivo,
        pedido=pedido, usuario=usuario, nota=nota[:255])


def stock_total(producto):
    return StockProducto.objects.filter(producto=producto).aggregate(s=Sum('cantidad'))['s'] or 0


# ───────────────────────── Velocidad de venta + reposición ─────────────────────────

def _nombres_de_producto(producto):
    """Nombres que representan al producto (su nombre + alias hacia productos homónimos),
    para casar líneas de pedido por relación y no solo por el FK exacto."""
    from productos.models import ProductoAlias
    nombres = set(ProductoAlias.objects.filter(producto__nombre__iexact=producto.nombre)
                  .values_list('nombre_externo', flat=True))
    if producto.nombre:
        nombres.add(producto.nombre)
    return list(nombres)


def consumo_dia(producto, dias=30):
    """Unidades vendidas por día (preventa + venta) en la ventana, casando el producto
    por relación de nombre/alias."""
    hoy = timezone.localdate()
    desde = hoy - timedelta(days=dias - 1)
    nombres = _nombres_de_producto(producto)
    total = (PedidoItem.objects.filter(
                Q(producto__nombre__iexact=producto.nombre) | Q(nombre__in=nombres),
                pedido__estado__in=ESTADOS_CONSUMO,
                pedido__fecha_pedido__date__range=(desde, hoy))
             .aggregate(s=Sum('cantidad'))['s'] or 0)
    return total / dias if dias else 0


def plan_reposicion(ventana=30):
    """Devuelve, por producto con reposición activa, el plan de compra: stock, consumo/día,
    días restantes, fecha sugerida de compra y cantidad sugerida. Ordenado por urgencia."""
    hoy = timezone.localdate()
    filas = []
    for cfg in ConfigReposicion.objects.filter(activo=True).select_related('producto'):
        p = cfg.producto
        stock = stock_total(p)
        consumo = consumo_dia(p, ventana)
        reorden_dias = cfg.dias_entrega + cfg.dias_seguridad

        if consumo > 0:
            dias_restantes = stock / consumo
            comprar_ya = dias_restantes <= reorden_dias
            fecha_sugerida = hoy + timedelta(days=max(0, round(dias_restantes - reorden_dias)))
            cantidad_sugerida = max(0, math.ceil(consumo * (cfg.dias_entrega + cfg.dias_cobertura) - stock))
        else:
            dias_restantes = None
            comprar_ya = False
            fecha_sugerida = None
            cantidad_sugerida = 0

        filas.append({
            'producto': p,
            'stock': stock,
            'consumo_dia': round(consumo, 2),
            'dias_restantes': round(dias_restantes, 1) if dias_restantes is not None else None,
            'lead_time': cfg.dias_entrega,
            'dias_seguridad': cfg.dias_seguridad,
            'dias_cobertura': cfg.dias_cobertura,
            'reorden_dias': reorden_dias,
            'comprar_ya': comprar_ya,
            'fecha_sugerida': fecha_sugerida,
            'cantidad_sugerida': cantidad_sugerida,
        })
    # Urgencia: primero los "comprar ya", luego por menos días restantes (None al final)
    filas.sort(key=lambda f: (not f['comprar_ya'],
                              f['dias_restantes'] if f['dias_restantes'] is not None else 9e9))
    return filas


# ───────────────────────── Auto-descuento al entregar ─────────────────────────

def _variante_para_item(item):
    """Mejor esfuerzo: si el producto tiene variantes, intenta casar el texto de variante
    del pedido (item.variante) con una VarianteProducto. Si no coincide, devuelve None
    (descuenta del stock sin variante)."""
    variantes = list(item.producto.variantes.filter(activo=True))
    if not variantes:
        return None
    txt = (item.variante or '').strip().lower()
    if not txt:
        return None
    # Coincidencia por palabras: la variante cuyos valores aparezcan todos en el texto
    mejor = None
    for v in variantes:
        partes = [p for p in v.clave.split('|') if p]
        if partes and all(p in txt for p in partes):
            mejor = v
            break
    return mejor


def _almacen_para_pedido(pedido):
    """Almacén del que se descuenta un pedido: el ligado a su integración (fuente), si no
    el marcado principal, si no el primer almacén activo. None si no hay almacenes."""
    activos = Almacen.objects.filter(activo=True)
    if pedido.integracion_id:
        a = activos.filter(integracion_id=pedido.integracion_id).first()
        if a:
            return a
    return activos.filter(es_principal=True).first() or activos.first()


@transaction.atomic
def sincronizar_stock_pedido(pedido):
    """Idempotente. Si el pedido está ENTREGADO y aún no descontó stock, descuenta cada
    ítem del almacén que le corresponde. Si dejó de estar entregado y ya había descontado,
    revierte (re-suma) esos movimientos. Evita doble descuento."""
    ya_descontado = MovimientoStock.objects.filter(
        pedido=pedido, motivo=MovimientoStock.MOTIVO_VENTA).exists()
    entregado = pedido.estado == Pedido.ESTADO_ENTREGADO

    if entregado and not ya_descontado:
        almacen = _almacen_para_pedido(pedido)
        if not almacen:
            return  # sin almacenes configurados: no hay de dónde descontar
        for it in pedido.items.all():
            if it.producto_id and it.cantidad:
                variante = _variante_para_item(it)
                aplicar_movimiento(it.producto, almacen, -it.cantidad,
                                   MovimientoStock.MOTIVO_VENTA, variante=variante, pedido=pedido,
                                   nota=f'Pedido {pedido.numero or pedido.external_id} entregado')
    elif not entregado and ya_descontado:
        # Revertir: re-sumar lo que se restó y borrar esos movimientos
        movs = list(MovimientoStock.objects.filter(
            pedido=pedido, motivo=MovimientoStock.MOTIVO_VENTA))
        for m in movs:
            aplicar_movimiento(m.producto, m.almacen, -m.delta,
                               MovimientoStock.MOTIVO_DEVOLUCION, variante=m.variante, pedido=pedido,
                               nota='Reversa: el pedido dejó de estar entregado')
        MovimientoStock.objects.filter(
            pedido=pedido, motivo=MovimientoStock.MOTIVO_VENTA).delete()
