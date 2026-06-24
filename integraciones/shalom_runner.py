# integraciones/shalom_runner.py
"""Orquesta una corrida de Shalom: etapa 1 (importar) → etapa 2 (validar),
con marca de agua de corte para no recorrer envíos ya entregados."""
import os

# Playwright (sync) crea un event loop en el hilo; sin esto, Django bloquea el ORM
# con SynchronousOnlyOperation. Es seguro aquí porque no hay concurrencia real.
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')

from datetime import timedelta

from django.utils import timezone

from . import shalom_scraper as sc
from .models import ConfigShalom, EnvioShalom, CorridaShalom


def _config(integ):
    cfg, _ = ConfigShalom.objects.get_or_create(integracion=integ)
    return cfg


def arreglar_mojibake(s):
    """Corrige texto UTF-8 mal decodificado como latin-1 (ej. 'AÃ©reo' → 'Aéreo')."""
    if s and 'Ã' in s:
        try:
            return s.encode('latin-1').decode('utf-8')
        except (UnicodeDecodeError, UnicodeEncodeError):
            return s
    return s


def _aplicar_estado(envio, estado_real):
    """Aplica la semántica de estado:
    - 'entregado' → entregado=True (ya lo recogió el cliente; sin alerta).
    - 'destino'   → llegó a la agencia: alerta para avisar al cliente (si no notificado)."""
    estado_l = (estado_real or '').lower()
    envio.entregado = 'entregado' in estado_l
    if envio.entregado:
        envio.en_alerta = False
    elif 'destino' in estado_l and not envio.notificado:
        envio.en_alerta = True


def _upsert_envio(integ, f):
    """Crea/actualiza un EnvioShalom desde una fila del listado. Devuelve (envio, creado)."""
    fecha = sc.parse_fecha(f.get('fecha', ''))
    envio, creado = EnvioShalom.objects.update_or_create(
        integracion=integ, orden=f['orden'], codigo=f['codigo'],
        defaults={
            'estado': f.get('estado', ''),
            'producto': f.get('producto', ''),
            'nombre': f.get('nombre', ''),
            'dni': f.get('dni', ''),
            'monto': f.get('monto', ''),
            'lugar_entrega': f.get('lugar_entrega', ''),
            'tipo_envio': f.get('tipo_envio', ''),
            'fecha_texto': f.get('fecha', ''),
            'fecha_pedido': fecha,
        },
    )
    return envio, creado


def _recalcular_corte(integ, cfg):
    """El corte = el envío PENDIENTE (no entregado) más antiguo. De ahí hacia atrás,
    todo está entregado, así que la próxima etapa 1 se detiene en ese punto."""
    pendiente = (EnvioShalom.objects
                 .filter(integracion=integ, entregado=False, fecha_pedido__isnull=False)
                 .order_by('fecha_pedido').first())
    if pendiente:
        cfg.corte_orden = pendiente.orden
        cfg.corte_codigo = pendiente.codigo
        cfg.corte_fecha = pendiente.fecha_pedido
    else:
        cfg.corte_orden = ''
        cfg.corte_codigo = ''
        cfg.corte_fecha = timezone.localdate() - timedelta(days=cfg.dias_atras)
    cfg.save(update_fields=['corte_orden', 'corte_codigo', 'corte_fecha'])


def correr(integ, tipo='manual', user=None, solo=None, orden=None, codigo=None):
    """Ejecuta la corrida. `solo` ∈ {None,'importar','validar'}.
    Si orden/codigo, valida solo ese envío."""
    from playwright.sync_api import sync_playwright

    cfg = _config(integ)
    if cfg.corriendo:
        return False, 'Ya hay una corrida en curso.'
    # Limpiar bandera de cancelación de corridas previas
    cfg.cancelar = False

    usuario = integ.api_key      # api_key = usuario Shalom
    password = integ.token       # token   = contraseña Shalom
    if not usuario or not password:
        return False, 'Faltan usuario/contraseña de Shalom.'

    sel = cfg.selectores()
    cfg.corriendo = True
    cfg.save(update_fields=['corriendo', 'cancelar'])
    corrida = CorridaShalom.objects.create(integracion=integ, tipo=tipo, por=user)
    nuevos = validados = entregados = 0
    ok = True
    mensaje = ''

    try:
        with sync_playwright() as p:
            ctx = sc.nuevo_contexto(p, integ)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                # ── Etapa 1: importar listado ──
                if solo != 'validar' and not orden:
                    corte = {'orden': cfg.corte_orden, 'codigo': cfg.corte_codigo, 'fecha': cfg.corte_fecha}
                    filas, alcanzo = sc.importar_listado(
                        page, sel, usuario, password, corte, cfg.max_paginas
                    )
                    for f in filas:
                        _, creado = _upsert_envio(integ, f)
                        if creado:
                            nuevos += 1

                # ── Etapa 2: validar pendientes ──
                if solo != 'importar':
                    sc.asegurar_sesion_rastreo(page, sel, usuario, password)
                    if orden and codigo:
                        qs = EnvioShalom.objects.filter(integracion=integ, orden=orden, codigo=codigo)
                    else:
                        qs = EnvioShalom.objects.filter(integracion=integ, entregado=False)
                    bloque = sc.random.randint(5, 15)
                    cont = 0
                    for envio in qs:
                        # Botón Detener: revisamos la bandera en BD cada iteración
                        if ConfigShalom.objects.filter(pk=cfg.pk, cancelar=True).exists():
                            mensaje = 'Detenido por el usuario. '
                            break
                        try:
                            estado_real = sc.validar_envio(page, sel, envio.orden, envio.codigo)
                            envio.estado_real = estado_real or 'NO_ENCONTRADO'
                            envio.ultima_validacion = timezone.now()
                            _aplicar_estado(envio, estado_real)
                            if envio.entregado:
                                entregados += 1
                            envio.save()
                            validados += 1
                        except Exception:
                            envio.estado_real = 'ERROR'
                            envio.save()
                            try:
                                sc.asegurar_sesion_rastreo(page, sel, usuario, password)
                            except Exception:
                                pass
                        cont += 1
                        if cont >= bloque:
                            sc.pausa_larga_con_actividad(page)
                            bloque = sc.random.randint(5, 15)
                            cont = 0
                        else:
                            sc.espera_humana(3, 6)

                # ── Recalcular corte ──
                _recalcular_corte(integ, cfg)
                mensaje += f'{nuevos} nuevos · {validados} validados · {entregados} entregados.'
            finally:
                ctx.close()
    except Exception as e:
        ok = False
        mensaje = f'Error: {e}'
    finally:
        cfg.corriendo = False
        cfg.cancelar = False
        cfg.ultima_corrida = timezone.now()
        cfg.ultimo_resultado = mensaje
        cfg.save(update_fields=['corriendo', 'cancelar', 'ultima_corrida', 'ultimo_resultado'])
        corrida.fin = timezone.now()
        corrida.ok = ok
        corrida.nuevos = nuevos
        corrida.validados = validados
        corrida.entregados = entregados
        corrida.mensaje = mensaje
        corrida.save()

    return ok, mensaje
