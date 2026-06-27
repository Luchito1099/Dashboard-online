# core/ia.py
"""Cliente unificado para las Conexiones de IA (ConexionIA). Soporta Anthropic (Claude)
y APIs compatibles con OpenAI (OpenAI, DeepSeek, OpenRouter, personalizada).

- probar(conexion): hace una llamada mínima para validar credenciales/modelo.
- llamar(conexion, prompt, texto): ejecuta una tarea y devuelve (respuesta, tin, tout),
  incrementando los contadores de consumo de la conexión.
"""
import requests
from django.utils import timezone


_BASES_OPENAI = {
    'openai': 'https://api.openai.com/v1',
    'deepseek': 'https://api.deepseek.com/v1',
    'openrouter': 'https://openrouter.ai/api/v1',
}


class IAError(Exception):
    pass


def _es_anthropic(conexion):
    return conexion.proveedor == 'anthropic'


def _base(conexion):
    if _es_anthropic(conexion):
        return (conexion.base_url or 'https://api.anthropic.com').rstrip('/')
    return (conexion.base_url or _BASES_OPENAI.get(conexion.proveedor) or '').rstrip('/')


def _llamar_crudo(conexion, mensajes, max_tokens=512):
    """Devuelve (texto, tokens_entrada, tokens_salida). Lanza IAError si falla."""
    api_key = conexion.api_key
    if not api_key:
        raise IAError('Falta la API key.')
    base = _base(conexion)
    if not base:
        raise IAError('Falta la URL base para este proveedor.')

    try:
        if _es_anthropic(conexion):
            r = requests.post(
                f'{base}/v1/messages',
                headers={'x-api-key': api_key, 'anthropic-version': '2023-06-01',
                         'content-type': 'application/json'},
                json={'model': conexion.modelo, 'max_tokens': max_tokens, 'messages': mensajes},
                timeout=40,
            )
            if r.status_code != 200:
                raise IAError(f'HTTP {r.status_code}: {r.text[:200]}')
            data = r.json()
            texto = ''.join(p.get('text', '') for p in data.get('content', []) if p.get('type') == 'text')
            uso = data.get('usage', {})
            return texto, int(uso.get('input_tokens', 0)), int(uso.get('output_tokens', 0))
        else:
            r = requests.post(
                f'{base}/chat/completions',
                headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
                json={'model': conexion.modelo, 'max_tokens': max_tokens, 'messages': mensajes},
                timeout=40,
            )
            if r.status_code != 200:
                raise IAError(f'HTTP {r.status_code}: {r.text[:200]}')
            data = r.json()
            texto = data['choices'][0]['message']['content']
            uso = data.get('usage', {})
            return texto, int(uso.get('prompt_tokens', 0)), int(uso.get('completion_tokens', 0))
    except requests.RequestException as e:
        raise IAError(f'No se pudo conectar: {e}')
    except (KeyError, IndexError, ValueError) as e:
        raise IAError(f'Respuesta no válida: {e}')


def probar(conexion):
    """Llamada mínima para validar la conexión. Devuelve (ok, mensaje) y guarda el estado."""
    try:
        texto, tin, tout = _llamar_crudo(conexion, [{'role': 'user', 'content': 'Responde solo: OK'}], max_tokens=16)
        ok, msg = True, f'OK · modelo {conexion.modelo} respondió ({tin}+{tout} tokens)'
    except IAError as e:
        ok, msg = False, str(e)
    conexion.ultimo_test_ok = ok
    conexion.ultimo_test_msg = msg[:255]
    conexion.ultimo_test_en = timezone.now()
    conexion.save(update_fields=['ultimo_test_ok', 'ultimo_test_msg', 'ultimo_test_en'])
    return ok, msg


def llamar(conexion, prompt, texto=''):
    """Ejecuta una tarea de IA y acumula el consumo en la conexión. Devuelve la respuesta."""
    contenido = f'{prompt}\n\n{texto}' if texto else prompt
    respuesta, tin, tout = _llamar_crudo(conexion, [{'role': 'user', 'content': contenido}])
    # Acumula consumo (F() evita condiciones de carrera)
    from django.db.models import F
    type(conexion).objects.filter(pk=conexion.pk).update(
        tokens_entrada=F('tokens_entrada') + tin,
        tokens_salida=F('tokens_salida') + tout,
        llamadas=F('llamadas') + 1,
    )
    return respuesta
