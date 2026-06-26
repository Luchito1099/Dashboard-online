# anuncios/connectors.py
"""Conexión DIRECTA a la Graph API de Meta. El ERP extrae los insights (diarios y
horarios) a nivel anuncio y los guarda reutilizando services.ingerir_payload (que
respeta incluir_en_extraccion). No depende de n8n para la extracción."""
import json
from datetime import timedelta

import requests
from django.utils import timezone

from . import services

GRAPH = 'https://graph.facebook.com'
TIMEOUT = 30

# action_type de Meta que cuentan como "resultado" (compra / lead / mensajes)
ACCIONES_RESULTADO = {
    'purchase', 'lead', 'omni_purchase',
    'offsite_conversion.fb_pixel_purchase',
    'onsite_conversion.messaging_conversation_started_7d',
    'onsite_conversion.messaging_first_reply',
}


def _resultados(actions):
    """Suma los valores de las acciones que consideramos 'resultado'."""
    if not actions:
        return 0
    total = 0
    for a in actions:
        if a.get('action_type') in ACCIONES_RESULTADO:
            try:
                total += int(float(a.get('value') or 0))
            except (TypeError, ValueError):
                pass
    return total


def _paginar(url, params):
    """Itera todas las páginas de un endpoint de insights (sigue paging.next)."""
    while url:
        resp = requests.get(url, params=params, timeout=TIMEOUT)
        if resp.status_code != 200:
            raise requests.RequestException(_error_msg(resp))
        data = resp.json()
        for row in data.get('data', []):
            yield row
        url = (data.get('paging') or {}).get('next')
        params = None   # 'next' ya trae todos los parámetros


def _error_msg(resp):
    try:
        err = resp.json().get('error', {})
        return f"Meta: {err.get('message', resp.status_code)} (código {err.get('code', '?')})"
    except ValueError:
        return f'HTTP {resp.status_code} de la Graph API.'


def probar_conexion(cuenta):
    """Valida token + ad_account llamando a /act_<id>?fields=name,currency."""
    if not cuenta.ad_account_id or not cuenta.access_token:
        return False, 'Falta el ad_account_id o el token.'
    url = f'{GRAPH}/{cuenta.api_version}/{cuenta.ad_account_id}'
    try:
        resp = requests.get(url, params={'fields': 'name,currency',
                                         'access_token': cuenta.access_token}, timeout=TIMEOUT)
    except requests.RequestException as e:
        return False, f'No se pudo conectar: {e}'
    if resp.status_code == 200:
        d = resp.json()
        return True, f"Conexión OK con «{d.get('name', cuenta.ad_account_id)}» ({d.get('currency', '')})."
    return False, _error_msg(resp)


def sincronizar(cuenta, dias=30):
    """Trae insights diarios + horarios (nivel ad) de los últimos N días y los guarda.
    Devuelve (ok, mensaje, resumen)."""
    if not cuenta.ad_account_id or not cuenta.access_token:
        return False, 'Falta el ad_account_id o el token.', {}

    hasta = timezone.localdate()
    desde = hasta - timedelta(days=dias - 1)
    time_range = json.dumps({'since': desde.isoformat(), 'until': hasta.isoformat()})
    base = {'access_token': cuenta.access_token, 'time_increment': 1,
            'level': 'ad', 'limit': 200, 'time_range': time_range}

    anuncios = {}

    def _ad(row):
        ad_id = row.get('ad_id')
        if ad_id not in anuncios:
            anuncios[ad_id] = {
                'campaign_id': row.get('campaign_id', ''), 'campaign_name': row.get('campaign_name', ''),
                'adset_id': row.get('adset_id', ''), 'adset_name': row.get('adset_name', ''),
                'ad_id': ad_id, 'ad_name': row.get('ad_name', ''),
                'insights_diarios': [], 'insights_horarios': [],
            }
        return anuncios[ad_id]

    url = f'{GRAPH}/{cuenta.api_version}/{cuenta.ad_account_id}/insights'
    try:
        # 1) Insights diarios
        params = dict(base, fields='campaign_id,campaign_name,adset_id,adset_name,ad_id,ad_name,'
                                    'spend,impressions,clicks,actions,account_currency')
        for row in _paginar(url, params):
            if not row.get('ad_id'):
                continue
            _ad(row)['insights_diarios'].append({
                'fecha': row.get('date_start'),
                'gasto': row.get('spend') or 0,
                'impresiones': row.get('impressions') or 0,
                'clicks': row.get('clicks') or 0,
                'resultados': _resultados(row.get('actions')),
                'moneda': row.get('account_currency') or '',
            })

        # 2) Insights horarios (breakdown por hora del anunciante)
        params = dict(base, fields='ad_id,spend,impressions,clicks',
                      breakdowns='hourly_stats_aggregated_by_advertiser_time_zone')
        for row in _paginar(url, params):
            if row.get('ad_id') not in anuncios:
                continue
            franja = row.get('hourly_stats_aggregated_by_advertiser_time_zone') or '00'
            try:
                hora = int(franja[:2])
            except ValueError:
                hora = 0
            _ad(row)['insights_horarios'].append({
                'fecha': row.get('date_start'), 'hora': hora,
                'gasto': row.get('spend') or 0,
                'impresiones': row.get('impressions') or 0,
                'clicks': row.get('clicks') or 0,
            })
    except requests.RequestException as e:
        return False, str(e), {}

    payload = {
        'cuenta': {'ad_account_id': cuenta.ad_account_id, 'nombre': cuenta.nombre},
        'anuncios': list(anuncios.values()),
    }
    resumen = services.ingerir_payload(payload)
    msg = (f"{resumen.get('anuncios', 0)} anuncio(s), "
           f"{resumen.get('insights_guardados', 0)} insight(s) guardado(s).")
    return True, msg, resumen
