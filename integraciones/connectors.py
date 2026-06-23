# integraciones/connectors.py
"""Lógica de conexión por proveedor. Por ahora solo valida la conexión
("Probar conexión"); la extracción real de pedidos llega en una etapa posterior.

Patrón extensible: registrar la función de prueba de cada proveedor en _PROBADORES.
"""
import hashlib
import hmac
from urllib.parse import urlencode

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


# ───────────────────────── OAuth de Shopify ─────────────────────────

def construir_url_autorizacion(integ, redirect_uri, state):
    """URL a la que se redirige al usuario para que autorice la app en Shopify."""
    dominio = _normalizar_dominio(integ.tienda_url)
    params = {
        'client_id': integ.api_key,
        'scope': integ.scopes or 'read_orders',
        'redirect_uri': redirect_uri,
        'state': state,
    }
    return f'https://{dominio}/admin/oauth/authorize?{urlencode(params)}'


def verificar_hmac(get_params, client_secret):
    """Valida el hmac que Shopify envía en el callback (firma con el client_secret)."""
    recibido = get_params.get('hmac', '')
    if not recibido or not client_secret:
        return False
    partes = sorted(f'{k}={v}' for k, v in get_params.items() if k != 'hmac')
    mensaje = '&'.join(partes)
    calculado = hmac.new(client_secret.encode(), mensaje.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(calculado, recibido)


def intercambiar_codigo(integ, code):
    """Cambia el 'code' del callback por un access token permanente. Devuelve el token o None."""
    dominio = _normalizar_dominio(integ.tienda_url)
    url = f'https://{dominio}/admin/oauth/access_token'
    try:
        resp = requests.post(url, json={
            'client_id': integ.api_key,
            'client_secret': integ.api_secret,
            'code': code,
        }, timeout=TIMEOUT)
    except requests.RequestException:
        return None
    if resp.status_code == 200:
        return resp.json().get('access_token')
    return None


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
    """Upsert de un pedido de Shopify (con sus productos) en la BD.
    Usa los campos estándar y completa lo que falte con note_attributes (formularios COD)."""
    from .models import Pedido, PedidoItem
    from django.utils.dateparse import parse_datetime

    cliente = o.get('customer') or {}
    envio = o.get('shipping_address') or o.get('billing_address') or {}
    # note_attributes → dict {nombre: valor} (datos del formulario EasySell)
    notas = {a.get('name'): a.get('value') for a in (o.get('note_attributes') or []) if a.get('name')}

    def estandar_o_nota(valor_estandar, *claves_nota):
        if valor_estandar:
            return valor_estandar
        for k in claves_nota:
            if notas.get(k):
                return notas[k]
        return ''

    nombre = (envio.get('name')
              or ' '.join(filter(None, [cliente.get('first_name'), cliente.get('last_name')])).strip()
              or notas.get('Nombres y Apellidos', ''))

    direccion = ' '.join(filter(None, [envio.get('address1'), envio.get('address2')])).strip()
    direccion = estandar_o_nota(direccion, 'Dirección')

    # Tipo de envío y si es express (del primer shipping_line)
    lineas_envio = o.get('shipping_lines') or []
    tipo_envio = lineas_envio[0].get('title', '') if lineas_envio else ''
    es_express = 'express' in tipo_envio.lower()

    # Costo de envío
    costo_envio = 0
    try:
        costo_envio = (o.get('total_shipping_price_set') or {}).get('shop_money', {}).get('amount') or 0
    except AttributeError:
        pass

    pedido, _creado = Pedido.objects.update_or_create(
        integracion=integ,
        external_id=str(o.get('id')),
        defaults={
            'numero': o.get('name', ''),
            'nombre_cliente': nombre,
            'telefono': estandar_o_nota(o.get('phone') or envio.get('phone') or cliente.get('phone'), 'Celular', 'Teléfono'),
            'email': o.get('email') or o.get('contact_email') or cliente.get('email') or '',
            'direccion': direccion,
            'distrito': estandar_o_nota(envio.get('city'), 'Distrito'),
            'provincia': estandar_o_nota(envio.get('province'), 'Provincia'),
            'pais': envio.get('country') or notas.get('country', ''),
            'latitud': envio.get('latitude'),
            'longitud': envio.get('longitude'),
            'total': o.get('total_price') or 0,
            'subtotal': o.get('subtotal_price') or 0,
            'descuentos': o.get('total_discounts') or 0,
            'costo_envio': costo_envio,
            'moneda': o.get('currency', ''),
            'metodo_pago': ', '.join(o.get('payment_gateway_names') or []),
            'estado_pago': o.get('financial_status') or '',
            'estado_envio': o.get('fulfillment_status') or 'unfulfilled',
            'tipo_envio': tipo_envio,
            'es_express': es_express,
            'tags': o.get('tags', ''),
            'nota': o.get('note') or notas.get('Confirmación de compra', ''),
            'order_status_url': o.get('order_status_url', ''),
            'fecha_pedido': parse_datetime(o['created_at']) if o.get('created_at') else None,
            'datos': o,
        },
    )

    # Productos: reemplazamos los items por los actuales del pedido
    pedido.items.all().delete()
    for li in o.get('line_items') or []:
        PedidoItem.objects.create(
            pedido=pedido,
            nombre=li.get('title') or li.get('name') or '',
            variante=li.get('variant_title') or '',
            sku=li.get('sku') or '',
            cantidad=li.get('quantity') or 1,
            precio=li.get('price') or 0,
            vendor=li.get('vendor') or '',
            product_id=str(li.get('product_id') or ''),
            variant_id=str(li.get('variant_id') or ''),
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
