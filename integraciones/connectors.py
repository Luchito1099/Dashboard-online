# integraciones/connectors.py
"""Lógica de conexión por proveedor. Por ahora solo valida la conexión
("Probar conexión"); la extracción real de pedidos llega en una etapa posterior.

Patrón extensible: registrar la función de prueba de cada proveedor en _PROBADORES.
"""
import requests
from django.utils import timezone

TIMEOUT = 8  # segundos


def _normalizar_dominio(tienda_url):
    """Quita esquema y barras para dejar solo 'xxx.myshopify.com'."""
    d = (tienda_url or '').strip()
    d = d.replace('https://', '').replace('http://', '')
    return d.strip('/')


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
