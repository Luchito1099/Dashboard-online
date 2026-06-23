# integraciones/connectors.py
"""Lógica de conexión por proveedor. Por ahora solo valida la conexión
("Probar conexión"); la extracción real de pedidos llega en una etapa posterior.

Patrón extensible: registrar la función de prueba de cada proveedor en _PROBADORES.
"""
import requests
from django.utils import timezone

TIMEOUT = 8  # segundos


def _normalizar_dominio(tienda_url):
    """Devuelve el dominio Shopify 'xxx.myshopify.com'.
    Acepta el dominio completo o solo el subdominio (ej. 'a67a2e-68')."""
    d = (tienda_url or '').strip()
    d = d.replace('https://', '').replace('http://', '').strip('/')
    if d and '.' not in d:
        d = f'{d}.myshopify.com'
    return d


def probar_shopify(integ):
    """Llama al endpoint shop.json de la Admin API para validar dominio + token."""
    dominio = _normalizar_dominio(integ.tienda_url)
    if not dominio or not integ.token:
        return False, 'Falta el dominio de la tienda o el access token.'

    version = integ.api_version or '2024-10'
    url = f'https://{dominio}/admin/api/{version}/shop.json'
    try:
        resp = requests.get(
            url,
            headers={'X-Shopify-Access-Token': integ.token},
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        return False, f'No se pudo conectar: {e}'

    if resp.status_code == 200:
        try:
            nombre = resp.json().get('shop', {}).get('name', dominio)
        except ValueError:
            nombre = dominio
        return True, f'Conexión OK con «{nombre}».'
    if resp.status_code in (401, 403):
        return False, 'Credenciales inválidas (token rechazado).'
    if resp.status_code == 404:
        return False, 'Dominio o versión de API no encontrados.'
    return False, f'Respuesta inesperada de Shopify (HTTP {resp.status_code}).'


# Registro de probadores por proveedor. Agregar aquí nuevos conectores.
_PROBADORES = {
    'shopify': probar_shopify,
}


def probar_conexion(integ):
    """Despacha al probador del proveedor, persiste el resultado y devuelve (ok, msg)."""
    probador = _PROBADORES.get(integ.proveedor)
    if probador is None:
        ok, msg = False, f'Conector para «{integ.get_proveedor_display()}» aún no implementado.'
    else:
        ok, msg = probador(integ)

    integ.ultimo_test_ok = ok
    integ.ultimo_test_msg = msg[:255]
    integ.ultimo_test_en = timezone.now()
    integ.save(update_fields=['ultimo_test_ok', 'ultimo_test_msg', 'ultimo_test_en'])
    return ok, msg


# ───────────────────────── Extracción de pedidos ─────────────────────────

def _parse_link_next(link_header):
    """Extrae la URL 'rel=next' del header Link de Shopify (paginación cursor)."""
    if not link_header:
        return None
    for parte in link_header.split(','):
        if 'rel="next"' in parte:
            inicio = parte.find('<') + 1
            fin = parte.find('>')
            if inicio > 0 and fin > inicio:
                return parte[inicio:fin]
    return None


def _guardar_pedido_shopify(integ, o):
    """Upsert de un pedido de Shopify en la tabla Pedido."""
    from .models import Pedido
    from django.utils.dateparse import parse_datetime

    cliente = o.get('customer') or {}
    nombre = ' '.join(filter(None, [cliente.get('first_name'), cliente.get('last_name')])).strip()

    Pedido.objects.update_or_create(
        integracion=integ,
        external_id=str(o.get('id')),
        defaults={
            'numero': o.get('name', ''),
            'nombre_cliente': nombre,
            'email': o.get('email') or cliente.get('email') or '',
            'total': o.get('total_price') or 0,
            'moneda': o.get('currency', ''),
            'estado_pago': o.get('financial_status') or '',
            'estado_envio': o.get('fulfillment_status') or 'unfulfilled',
            'fecha_pedido': parse_datetime(o['created_at']) if o.get('created_at') else None,
            'datos': o,
        },
    )


def extraer_pedidos_shopify(integ):
    """Trae TODOS los pedidos (status=any) paginando con el cursor de Shopify.
    Devuelve (ok, msg, total)."""
    dominio = _normalizar_dominio(integ.tienda_url)
    if not dominio or not integ.token:
        return False, 'Falta el subdominio de la tienda o el access token.', 0

    version = integ.api_version or '2024-10'
    url = f'https://{dominio}/admin/api/{version}/orders.json'
    params = {'status': 'any', 'limit': 250}
    headers = {'X-Shopify-Access-Token': integ.token}
    total = 0

    try:
        while url:
            resp = requests.get(url, params=params, headers=headers, timeout=30)
            if resp.status_code in (401, 403):
                return False, 'Credenciales inválidas (token rechazado).', total
            if resp.status_code != 200:
                return False, f'Error de Shopify (HTTP {resp.status_code}).', total

            pedidos = resp.json().get('orders', [])
            for o in pedidos:
                _guardar_pedido_shopify(integ, o)
                total += 1

            # La siguiente página viene en el header Link; params solo en la 1ª llamada
            url = _parse_link_next(resp.headers.get('Link'))
            params = None
    except requests.RequestException as e:
        return False, f'No se pudo conectar: {e}', total

    return True, f'{total} pedido(s) sincronizado(s).', total


_EXTRACTORES = {
    'shopify': extraer_pedidos_shopify,
}


def extraer_pedidos(integ):
    """Despacha al extractor del proveedor, persiste el resultado y devuelve (ok, msg, total)."""
    extractor = _EXTRACTORES.get(integ.proveedor)
    if extractor is None:
        ok, msg, total = False, f'Extracción para «{integ.get_proveedor_display()}» aún no implementada.', 0
    else:
        ok, msg, total = extractor(integ)

    integ.ultimo_sync_ok = ok
    integ.ultimo_sync_msg = msg[:255]
    integ.ultimo_sync_en = timezone.now()
    integ.save(update_fields=['ultimo_sync_ok', 'ultimo_sync_msg', 'ultimo_sync_en'])
    return ok, msg, total
