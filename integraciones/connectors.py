# integraciones/connectors.py
"""Lógica de conexión por proveedor. Por ahora solo valida la conexión
("Probar conexión"); la extracción real de pedidos llega en una etapa posterior.

Patrón extensible: registrar la función de prueba de cada proveedor en _PROBADORES.
"""
import base64
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


# ───────────────────────── Webhooks (tiempo real) ─────────────────────────

def verificar_webhook(body_bytes, hmac_header, secret):
    """Valida la firma HMAC-SHA256 (base64) que Shopify envía en cada webhook.
    Se firma con el Client Secret de la app."""
    if not hmac_header or not secret:
        return False
    digest = hmac.new(secret.encode(), body_bytes, hashlib.sha256).digest()
    calculado = base64.b64encode(digest).decode()
    return hmac.compare_digest(calculado, hmac_header)


def registrar_webhooks_shopify(integ, address):
    """Registra los webhooks orders/create y orders/updated apuntando a `address`.
    Devuelve (ok, msg)."""
    dominio = _normalizar_dominio(integ.tienda_url)
    if not dominio or not integ.token:
        return False, 'Falta el subdominio o el access token.'
    version = integ.api_version or '2024-10'
    headers = {'X-Shopify-Access-Token': integ.token, 'Content-Type': 'application/json'}
    creados = 0
    for topic in ('orders/create', 'orders/updated'):
        try:
            resp = requests.post(
                f'https://{dominio}/admin/api/{version}/webhooks.json',
                headers=headers,
                json={'webhook': {'topic': topic, 'address': address, 'format': 'json'}},
                timeout=TIMEOUT,
            )
        except requests.RequestException as e:
            return False, f'No se pudo conectar: {e}'
        # 201 creado; 422 suele ser "ya existe" (lo damos por bueno)
        if resp.status_code == 201:
            creados += 1
        elif resp.status_code == 422 and 'taken' in resp.text.lower():
            creados += 1
        elif resp.status_code in (401, 403):
            return False, 'Credenciales inválidas (token rechazado).'
        else:
            return False, f'Error al registrar «{topic}» (HTTP {resp.status_code}): {resp.text[:160]}'
    return True, f'Webhooks activos ({creados}/2). Los pedidos nuevos llegarán solos.'


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


def _norm_txt(s):
    """Normaliza un texto para comparar (sin espacios extra ni mayúsculas)."""
    return ' '.join((s or '').split()).lower()


def _extraer_utm(o, notas):
    """Saca la atribución publicitaria del pedido: del landing_site (query params) y,
    como respaldo, de los note_attributes del formulario. Devuelve los 4 campos UTM."""
    from urllib.parse import urlparse, parse_qs
    utm = {'utm_source': '', 'utm_campaign': '', 'utm_content': '', 'ad_id_origen': ''}

    landing = o.get('landing_site') or o.get('referring_site') or ''
    if landing:
        try:
            qs = parse_qs(urlparse(landing).query)
            utm['utm_source'] = (qs.get('utm_source') or [''])[0]
            utm['utm_campaign'] = (qs.get('utm_campaign') or [''])[0]
            utm['utm_content'] = (qs.get('utm_content') or [''])[0]
            for k in ('ad_id', 'adid', 'ad'):
                if qs.get(k):
                    utm['ad_id_origen'] = qs[k][0]
                    break
        except (ValueError, KeyError):
            pass

    for k, v in (notas or {}).items():
        kl = (k or '').lower()
        if not utm['utm_source'] and kl == 'utm_source':
            utm['utm_source'] = v or ''
        if not utm['utm_campaign'] and kl in ('utm_campaign', 'campaign', 'campaña'):
            utm['utm_campaign'] = v or ''
        if not utm['utm_content'] and kl in ('utm_content', 'ad', 'anuncio'):
            utm['utm_content'] = v or ''
        if not utm['ad_id_origen'] and kl in ('ad_id', 'adid'):
            utm['ad_id_origen'] = v or ''

    return {
        'utm_source': (utm['utm_source'] or '')[:120],
        'utm_campaign': (utm['utm_campaign'] or '')[:200],
        'utm_content': (utm['utm_content'] or '')[:200],
        'ad_id_origen': (utm['ad_id_origen'] or '')[:64],
    }


def _resolver_producto(integ, nombre, sku, external_product_id):
    """Resuelve el Producto canónico de una línea de pedido usando ProductoAlias
    (por id externo o por nombre, de esta tienda o global) y, en último caso, por SKU."""
    from django.db.models import Q
    from productos.models import Producto, ProductoAlias

    if external_product_id:
        a = (ProductoAlias.objects.filter(external_product_id=str(external_product_id))
             .select_related('producto').first())
        if a:
            return a.producto
    if nombre:
        a = (ProductoAlias.objects
             .filter(Q(integracion=integ) | Q(integracion__isnull=True), nombre_externo__iexact=nombre.strip())
             .select_related('producto').first())
        if a:
            return a.producto
    if sku:
        p = Producto.objects.filter(sku__iexact=sku.strip()).first()
        if p:
            return p
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

    utm = _extraer_utm(o, notas)

    pedido, _creado = Pedido.objects.update_or_create(
        integracion=integ,
        external_id=str(o.get('id')),
        defaults={
            'numero': o.get('name', ''),
            'utm_source': utm['utm_source'],
            'utm_campaign': utm['utm_campaign'],
            'utm_content': utm['utm_content'],
            'ad_id_origen': utm['ad_id_origen'],
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

    # Productos: reemplazamos los items por los actuales del pedido (vinculando al
    # catálogo canónico vía ProductoAlias cuando se reconoce).
    pedido.items.all().delete()
    for li in o.get('line_items') or []:
        nombre_item = li.get('title') or li.get('name') or ''
        sku_item = li.get('sku') or ''
        product_id = str(li.get('product_id') or '')
        PedidoItem.objects.create(
            pedido=pedido,
            producto=_resolver_producto(integ, nombre_item, sku_item, product_id),
            nombre=nombre_item,
            variante=li.get('variant_title') or '',
            sku=sku_item,
            cantidad=li.get('quantity') or 1,
            precio=li.get('price') or 0,
            vendor=li.get('vendor') or '',
            product_id=product_id,
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
