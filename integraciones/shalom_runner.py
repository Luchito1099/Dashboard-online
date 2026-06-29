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


def _progreso(cfg, texto):
    """Actualiza el titular de avance, ACUMULA la línea en el búfer de log (para que el
    panel no pierda pasos rápidos entre lecturas) y refresca el latido, para que una
    corrida muerta no deje el flag 'corriendo' trabado."""
    txt = texto[:255]
    cfg.progreso = txt
    cfg.latido = timezone.now()
    log = list(cfg.log_lineas or [])
    seq = (log[-1][0] + 1) if log else 1
    log.append([seq, timezone.localtime().strftime('%H:%M:%S'), txt])
    cfg.log_lineas = log[-300:]   # tope para no crecer sin límite
    cfg.save(update_fields=['progreso', 'latido', 'log_lineas'])


def _captura(cfg, page, etiqueta):
    """Guarda un PNG de lo que el navegador ve ahora y lo registra para que el panel lo
    muestre. Nunca rompe la corrida si falla (la captura es solo ayuda visual)."""
    import os
    from django.conf import settings
    try:
        rel = os.path.join('shalom_capturas', str(cfg.integracion_id))
        carpeta = os.path.join(settings.MEDIA_ROOT, rel)
        os.makedirs(carpeta, exist_ok=True)
        caps = list(cfg.capturas or [])
        seq = (caps[-1][0] + 1) if caps else 1
        page.screenshot(path=os.path.join(carpeta, f'{seq}.png'), full_page=False)
        try:
            url_pag = page.url
        except Exception:
            url_pag = ''
        caps.append([seq, timezone.localtime().strftime('%H:%M:%S'), etiqueta[:80], url_pag])
        cfg.capturas = caps[-20:]   # guardamos referencia a las últimas 20
        cfg.save(update_fields=['capturas'])
    except Exception:
        pass


def _limpiar_capturas(integracion_id):
    """Borra las capturas de la corrida anterior (carpeta + lista)."""
    import os
    import shutil
    from django.conf import settings
    shutil.rmtree(os.path.join(settings.MEDIA_ROOT, 'shalom_capturas', str(integracion_id)),
                  ignore_errors=True)


def arreglar_mojibake(s):
    """Corrige texto UTF-8 mal decodificado como latin-1 (ej. 'AÃ©reo' → 'Aéreo')."""
    if s and 'Ã' in s:
        try:
            return s.encode('latin-1').decode('utf-8')
        except (UnicodeDecodeError, UnicodeEncodeError):
            return s
    return s


# Estados terminales que NO son "entregado" pero ya no deben re-validarse ni mover el corte
TERMINAL_REGEX = r'retorn|cambio de destino|cambió de destino|descart|devuel|rechaz'


def _es_terminal(estado_real):
    e = (estado_real or '').lower()
    if 'entregado' in e:
        return True
    return any(t in e for t in ('retorn', 'cambio de destino', 'cambió de destino', 'descart', 'devuel', 'rechaz'))


def _aplicar_estado(envio, estado_real):
    """Semántica de estado:
    - 'entregado' → entregado=True (ya lo recogió el cliente; sin alerta).
    - terminal (retornó/cambió de destino/etc) → cerrado: no se re-valida ni alerta.
    - 'en destino' → llegó a la agencia: alerta para avisar al cliente (si no notificado)."""
    estado_l = (estado_real or '').lower()
    envio.entregado = 'entregado' in estado_l
    if _es_terminal(estado_real):
        envio.en_alerta = False
    elif 'en destino' in estado_l and not envio.notificado:
        envio.en_alerta = True


def _abiertos(integ):
    """Envíos 'abiertos' = no entregados y sin estado terminal. Son los que se
    revalidan y los que definen el corte. Excluye retornos/cambios de destino/etc."""
    from .models import EnvioShalom
    return (EnvioShalom.objects
            .filter(integracion=integ, entregado=False)
            .exclude(estado_real__iregex=TERMINAL_REGEX))


def _upsert_envio(integ, f, palabra_entregado='entregado'):
    """Crea/actualiza un EnvioShalom desde una fila del listado. Devuelve (envio, creado).

    Si el listado de etapa 1 ya marca el envío como ENTREGADO, lo cerramos aquí:
    así no se vuelve a buscar en etapa 2 (es la 'referencia de corte' del usuario)."""
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
    estado_listado = (f.get('estado', '') or '').lower()
    if palabra_entregado and palabra_entregado.lower() in estado_listado and not envio.entregado:
        envio.entregado = True
        envio.en_alerta = False
        if not envio.estado_real:
            envio.estado_real = f.get('estado', '')
        envio.save(update_fields=['entregado', 'en_alerta', 'estado_real'])
    return envio, creado


def _recalcular_corte(integ, cfg):
    """El corte = el envío PENDIENTE (no entregado) más antiguo. De ahí hacia atrás,
    todo está entregado, así que la próxima etapa 1 se detiene en ese punto."""
    pendiente = (_abiertos(integ)
                 .filter(fecha_pedido__isnull=False)
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
        # Auto-destrabe: si no hay latido reciente, la corrida anterior murió
        # (redeploy, crash, servidor reiniciado) y dejó el flag trabado.
        vivo = cfg.latido and (timezone.now() - cfg.latido) < timedelta(minutes=5)
        if vivo:
            return False, 'Ya hay una corrida en curso.'
        # corrida zombie: la damos por muerta y continuamos
    # Limpiar bandera de cancelación de corridas previas
    cfg.cancelar = False

    usuario = integ.api_key      # api_key = usuario Shalom
    password = integ.token       # token   = contraseña Shalom
    if not usuario or not password:
        return False, 'Faltan usuario/contraseña de Shalom.'

    sel = cfg.selectores()
    _limpiar_capturas(integ.id)
    cfg.corriendo = True
    cfg.log_lineas = []   # log limpio para esta corrida (el panel detecta el reinicio)
    cfg.capturas = []     # capturas limpias para esta corrida
    cfg.save(update_fields=['corriendo', 'cancelar', 'log_lineas', 'capturas'])
    corrida = CorridaShalom.objects.create(integracion=integ, tipo=tipo, por=user)
    nuevos = validados = entregados = 0
    ok = True
    mensaje = ''

    try:
        _progreso(cfg, 'Abriendo navegador…')
        with sync_playwright() as p:
            ctx = sc.nuevo_contexto(p, integ)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                # ── Etapa 1: importar listado ──
                if solo != 'validar' and not orden:
                    _progreso(cfg, 'Etapa 1: iniciando sesión en pro.shalom.pe…')
                    corte = {'orden': cfg.corte_orden, 'codigo': cfg.corte_codigo, 'fecha': cfg.corte_fecha}

                    def _on_pagina(pagina, filas):
                        _progreso(cfg, f'Etapa 1: página {pagina} leída · {len(filas)} envíos en esta página…')

                    log1 = lambda m: _progreso(cfg, f'Etapa 1: {m}')
                    filas, alcanzo = sc.importar_listado(
                        page, sel, usuario, password, corte, cfg.max_paginas,
                        on_pagina=_on_pagina, log=log1
                    )
                    _progreso(cfg, f'Etapa 1: guardando {len(filas)} envíos leídos en la base…')
                    palabra_ent = sel.get('palabra_entregado', 'entregado')
                    for f in filas:
                        _, creado = _upsert_envio(integ, f, palabra_ent)
                        if creado:
                            nuevos += 1
                    _progreso(cfg, f'Etapa 1 lista: {len(filas)} leídos, {nuevos} nuevos.')

                # ── Etapa 2: validar pendientes ──
                if solo != 'importar':
                    usar_listado = sel.get('metodo_rastreo', 'listado') == 'listado'
                    log2 = lambda m: _progreso(cfg, f'Etapa 2: {m}')
                    cap = lambda pg, et: _captura(cfg, pg, et)
                    if usar_listado:
                        # Método nuevo: reutiliza la sesión logueada de pro.shalom.pe (la misma
                        # página de etapa 1, donde el login SÍ entra) y rastrea con la lupita.
                        _progreso(cfg, 'Etapa 2: preparando rastreo desde el listado (lupita)…')
                        sc.abrir_seguimiento(page, sel, usuario, password, log=log2)
                        pv = page
                    else:
                        # Método viejo: pestaña limpia hacia shalom.com.pe/rastrea (cross-dominio).
                        _progreso(cfg, 'Etapa 2: preparando rastreo…')
                        pv = ctx.new_page()
                        sc.asegurar_sesion_rastreo(pv, sel, usuario, password, log=log2, cap=cap)

                    def _validar(_envio, _log, _cap):
                        if usar_listado:
                            return sc.validar_envio_listado(
                                pv, sel, _envio.orden, _envio.codigo, usuario, password, log=_log, cap=_cap)
                        return sc.validar_envio(pv, sel, _envio.orden, _envio.codigo, log=_log, cap=_cap)

                    def _reconectar():
                        if usar_listado:
                            sc.abrir_seguimiento(pv, sel, usuario, password, log=log2)
                        else:
                            sc.asegurar_sesion_rastreo(pv, sel, usuario, password, log=log2, cap=cap)

                    if orden and codigo:
                        qs = EnvioShalom.objects.filter(integracion=integ, orden=orden, codigo=codigo)
                    else:
                        qs = _abiertos(integ)
                    total_val = qs.count()
                    bloque = sc.random.randint(5, 15)
                    cont = 0
                    for i, envio in enumerate(qs, 1):
                        # Botón Detener: revisamos la bandera en BD cada iteración
                        if ConfigShalom.objects.filter(pk=cfg.pk, cancelar=True).exists():
                            mensaje = 'Detenido por el usuario. '
                            break
                        _progreso(cfg, f'[{i}/{total_val}] Consultando {envio.orden}/{envio.codigo} ({envio.nombre or "sin nombre"})…')
                        log_envio = lambda m, _i=i: _progreso(cfg, f'[{_i}/{total_val}] {m}')

                        def _guardar_estado(estado_real, _i=i, _e=envio):
                            _e.estado_real = estado_real or 'NO_ENCONTRADO'
                            _e.ultima_validacion = timezone.now()
                            _aplicar_estado(_e, estado_real)
                            _e.save()
                            _progreso(cfg, f'[{_i}/{total_val}] {_e.orden}/{_e.codigo} → {_e.estado_real}')

                        cap_envio = lambda pg, et, _i=i: _captura(cfg, pg, f'[{_i}] {et}')
                        try:
                            estado_real = _validar(envio, log_envio, cap_envio)
                            _guardar_estado(estado_real)
                            if envio.entregado:
                                entregados += 1
                            validados += 1
                        except Exception:
                            # Sesión caída u otro error: reconectamos y REINTENTAMOS este mismo envío.
                            _progreso(cfg, f'[{i}/{total_val}] {envio.orden}/{envio.codigo} → reconectando…')
                            try:
                                _reconectar()
                                estado_real = _validar(envio, log_envio, cap_envio)
                                _guardar_estado(estado_real)
                                if envio.entregado:
                                    entregados += 1
                                validados += 1
                            except Exception:
                                envio.estado_real = 'ERROR'
                                envio.save()
                                _progreso(cfg, f'[{i}/{total_val}] {envio.orden}/{envio.codigo} → ERROR')
                        cont += 1
                        if cont >= bloque:
                            _progreso(cfg, f'— Pausa de bloque ({cont} pedidos procesados, {validados} ok, {entregados} entregados) —')
                            sc.pausa_larga_con_actividad(pv)
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
        cfg.progreso = ''
        cfg.ultima_corrida = timezone.now()
        cfg.ultimo_resultado = mensaje
        cfg.save(update_fields=['corriendo', 'cancelar', 'progreso', 'ultima_corrida', 'ultimo_resultado'])
        corrida.fin = timezone.now()
        corrida.ok = ok
        corrida.nuevos = nuevos
        corrida.validados = validados
        corrida.entregados = entregados
        corrida.mensaje = mensaje
        corrida.save()

    return ok, mensaje
