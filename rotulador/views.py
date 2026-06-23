# rotulador/views.py
import json

import requests
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseNotAllowed
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_http_methods

from integraciones.models import Pedido
from .models import Rotulo, RotuladorConfig, DEFAULT_PROMPT


# ───────────────────────── Helpers ─────────────────────────

def _cfg_publica(cfg):
    """Config para el front (la key se enmascara, nunca se envía en claro)."""
    key = cfg.ai_api_key or ''
    return {
        'brand': cfg.brand,
        'initial': cfg.initial,
        'accent': cfg.accent,
        'label_style': cfg.label_style,
        'visual': cfg.visual or {},
        'logos': cfg.logos or [],
        'active_logo': cfg.active_logo,
        'productos': cfg.productos or [],
        'ai_provider': cfg.ai_provider,
        'ai_model': cfg.ai_model,
        'ai_key_set': bool(key),
        'ai_key_mask': (f'••••{key[-4:]}' if len(key) > 4 else ('••••' if key else '')),
        'prompt': cfg.prompt or DEFAULT_PROMPT,
    }


def _buscar_dni_en_notas(datos):
    """Busca un DNI/documento en los note_attributes del pedido Shopify."""
    notas = (datos or {}).get('note_attributes') or []
    for a in notas:
        nombre = (a.get('name') or '').lower()
        if 'dni' in nombre or 'documento' in nombre:
            return a.get('value') or ''
    return ''


def _mapear_pedido(p):
    """Mapea un integraciones.Pedido a la forma de un rótulo (para importar)."""
    items = list(p.items.all())
    producto = ' + '.join(f'{i.cantidad}× {i.nombre}' for i in items) if items else ''
    cantidad = sum(i.cantidad for i in items) or 1
    destino = ', '.join(filter(None, [p.direccion, p.distrito, p.provincia]))
    return {
        'pedido_id': p.id,
        'numero': p.numero,
        'nombres': p.nombre_cliente,
        'destino': destino,
        'celular': p.telefono,
        'dni': _buscar_dni_en_notas(p.datos),
        'producto': producto,
        'cantidad': cantidad,
        'distrito': p.distrito,
        'provincia': p.provincia,
    }


# ───────────────────────── Vistas ─────────────────────────

@login_required
def index(request):
    """Página del rotulador (todos los usuarios autenticados)."""
    return render(request, 'rotulador/index.html')


@login_required
@require_http_methods(['GET', 'POST'])
def api_rotulos(request):
    """GET: lista de rótulos. POST: crea un rótulo nuevo."""
    if request.method == 'GET':
        return JsonResponse({'rotulos': [r.to_dict() for r in Rotulo.objects.all()]})

    datos = json.loads(request.body or '{}')
    r = Rotulo.objects.create(
        nombres=datos.get('nombres', '').strip(),
        destino=datos.get('destino', '').strip(),
        agencia=datos.get('agencia', '').strip(),
        celular=datos.get('celular', '').strip(),
        dni=datos.get('dni', '').strip(),
        producto=datos.get('producto', '').strip(),
        cantidad=int(datos.get('cantidad') or 1),
        origen=datos.get('origen', 'manual'),
        pedido_id=datos.get('pedido_id') or None,
        creado_por=request.user,
    )
    return JsonResponse(r.to_dict(), status=201)


@login_required
@require_http_methods(['PUT', 'DELETE'])
def api_rotulo_detail(request, rotulo_id):
    """PUT: edita un rótulo. DELETE: lo elimina."""
    r = get_object_or_404(Rotulo, id=rotulo_id)
    if request.method == 'DELETE':
        r.delete()
        return JsonResponse({'ok': True})

    datos = json.loads(request.body or '{}')
    for campo in ('nombres', 'destino', 'agencia', 'celular', 'dni', 'producto'):
        if campo in datos:
            setattr(r, campo, (datos.get(campo) or '').strip())
    if 'cantidad' in datos:
        r.cantidad = int(datos.get('cantidad') or 1)
    r.save()
    return JsonResponse(r.to_dict())


@login_required
def api_pedidos(request):
    """Pedidos sincronizados aún no importados como rótulo, listos para importar."""
    pedidos = (
        Pedido.objects.filter(rotulos__isnull=True)
        .prefetch_related('items')
        .order_by('-fecha_pedido')[:300]
    )
    return JsonResponse({'pedidos': [_mapear_pedido(p) for p in pedidos]})


@login_required
@require_http_methods(['GET', 'POST'])
def api_config(request):
    """GET: config pública (key enmascarada). POST: guarda config."""
    cfg = RotuladorConfig.get_solo()
    if request.method == 'GET':
        return JsonResponse(_cfg_publica(cfg))

    datos = json.loads(request.body or '{}')
    for campo in ('brand', 'initial', 'accent', 'label_style', 'ai_provider', 'ai_model', 'prompt'):
        if campo in datos and datos[campo] is not None:
            setattr(cfg, campo, datos[campo])
    for campo in ('visual', 'logos', 'productos'):
        if campo in datos and datos[campo] is not None:
            setattr(cfg, campo, datos[campo])
    if 'active_logo' in datos:
        cfg.active_logo = datos['active_logo']
    # La key solo se actualiza si llega con contenido nuevo
    nueva_key = (datos.get('ai_api_key') or '').strip()
    if nueva_key:
        cfg.ai_api_key = nueva_key
    cfg.save()
    return JsonResponse(_cfg_publica(cfg))


@login_required
def api_extraer(request):
    """Proxy IA: extrae datos de envío de un texto o imagen usando Anthropic.
    La API key vive en el servidor (config o env), nunca en el navegador."""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    cfg = RotuladorConfig.get_solo()
    api_key = cfg.ai_api_key or getattr(settings, 'ANTHROPIC_API_KEY', '') or ''
    if not api_key:
        return JsonResponse({'error': 'Configura la API key en la pestaña IA.'}, status=400)

    datos = json.loads(request.body or '{}')
    texto = datos.get('text', '')
    imagen = datos.get('image_base64')
    media_type = datos.get('media_type', 'image/jpeg')
    prompt = cfg.prompt or DEFAULT_PROMPT

    # Construcción del contenido (texto o imagen)
    if imagen:
        content = [
            {'type': 'image', 'source': {'type': 'base64', 'media_type': media_type, 'data': imagen}},
            {'type': 'text', 'text': f'{prompt}\n\nAnaliza la imagen y extrae los datos del pedido.'},
        ]
    else:
        content = f'{prompt}\n\nTEXTO:\n{texto}'

    try:
        resp = requests.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
                'content-type': 'application/json',
            },
            json={
                'model': cfg.ai_model or 'claude-haiku-4-5-20251001',
                'max_tokens': 1024,
                'messages': [{'role': 'user', 'content': content}],
            },
            timeout=40,
        )
    except requests.RequestException as e:
        return JsonResponse({'error': f'No se pudo conectar con la IA: {e}'}, status=502)

    if resp.status_code != 200:
        return JsonResponse({'error': f'IA respondió HTTP {resp.status_code}: {resp.text[:300]}'}, status=502)

    # Texto de la respuesta → JSON
    try:
        partes = resp.json().get('content', [])
        texto_ia = ''.join(p.get('text', '') for p in partes if p.get('type') == 'text')
    except (ValueError, AttributeError):
        return JsonResponse({'error': 'Respuesta de IA no válida.'}, status=502)

    extraido = _extraer_json(texto_ia)
    if extraido is None:
        return JsonResponse({'error': 'No se pudo extraer datos del texto.'}, status=422)
    return JsonResponse({'data': extraido})


def _extraer_json(texto):
    """Extrae el primer objeto JSON de un string (la IA a veces añade texto)."""
    if not texto:
        return None
    inicio = texto.find('{')
    fin = texto.rfind('}')
    if inicio == -1 or fin <= inicio:
        return None
    try:
        return json.loads(texto[inicio:fin + 1])
    except ValueError:
        return None
