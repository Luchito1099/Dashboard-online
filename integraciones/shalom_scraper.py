# integraciones/shalom_scraper.py
"""Scraper de Shalom con Playwright (headless + anti-detección).
Dos etapas:
  1) importar_listado  → lee el listado paginado de pro.shalom.pe (con corte temprano)
  2) validar_envio     → consulta el estado real en shalom.com.pe/rastrea

Parametrizado por los selectores/URLs de ConfigShalom.selectores().
"""
import random
import time
from datetime import datetime
from pathlib import Path

from django.conf import settings

USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
)

# Script para ocultar señales de automatización
_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['es-PE','es']});
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
window.chrome = window.chrome || {runtime: {}};
"""


def espera_humana(minimo=1.0, maximo=2.5):
    time.sleep(random.uniform(minimo, maximo))


def esperar_carga(page):
    """Espera tolerante: 'networkidle' suele colgarse en sitios con conexiones
    persistentes. Usamos 'domcontentloaded' y damos un margen sin reventar si falla."""
    try:
        page.wait_for_load_state('domcontentloaded', timeout=20000)
    except Exception:
        pass
    espera_humana(0.5, 1.2)


def movimiento_humano(page):
    try:
        page.mouse.move(random.randint(100, 900), random.randint(100, 600), steps=random.randint(5, 15))
        espera_humana(0.3, 0.8)
        page.mouse.wheel(0, random.randint(-150, 250))
        espera_humana(0.3, 0.7)
    except Exception:
        pass


def _noop(_):
    pass


def _nocap(_page, _etiqueta):
    pass


def _escribir_humano(page, selector, texto, rapido=False, log=_noop, etiqueta=''):
    """Escribe carácter por carácter disparando eventos de teclado reales.
    `fill()` setea el valor de golpe sin keydown/keyup/input, y varios formularios
    anti-bot (como el de Shalom) no validan/activan el submit sin esos eventos.
    `rapido=False` (default) va más lento: úsalo para la contraseña.
    `etiqueta` (ej. 'la contraseña') se muestra en el log paso a paso."""
    if etiqueta:
        log(f'Escribiendo {etiqueta} despacio, carácter por carácter…')
    loc = page.locator(selector).first
    loc.click()
    espera_humana(0.3, 0.7)
    loc.fill('')   # limpiar por si el contexto persistente dejó algo
    espera_humana(0.2, 0.5)
    dmin, dmax = (60, 140) if rapido else (110, 240)
    loc.press_sequentially(texto, delay=random.uniform(dmin, dmax))
    espera_humana(0.4, 0.9)


def _calentar(page, urls, log=_noop):
    """Navega una secuencia de URLs (Google → home Shalom → login) antes del login,
    con movimientos/pausas humanas. Da referrer y cookies de navegación legítima,
    como cuando el usuario llega 'a mano'. URLs vacías se omiten."""
    visitar = [u for u in urls if u]
    total = len(visitar)
    for i, url in enumerate(visitar, 1):
        sitio = url.split('//')[-1].split('/')[0]   # dominio corto para el log
        log(f'Calentamiento {i}/{total}: entrando a {sitio}…')
        try:
            ir_a(page, url)
        except Exception:
            log(f'Calentamiento {i}/{total}: no se pudo abrir {sitio}, continúo.')
            continue
        movimiento_humano(page)
        espera_humana(1.2, 2.5)


def pausa_larga_con_actividad(page, minimo=15, maximo=20):
    """Pausa entre bloques simulando distracción (mueve mouse/scroll)."""
    duracion = random.uniform(minimo, maximo)
    transcurrido = 0
    while transcurrido < duracion:
        paso = random.uniform(3, 6)
        time.sleep(min(paso, duracion - transcurrido))
        transcurrido += paso
        movimiento_humano(page)


def nuevo_contexto(playwright, integracion):
    """Lanza un contexto persistente headless con medidas anti-detección.
    El contexto persistente reutiliza cookies/sesión por integración."""
    user_dir = Path(settings.BASE_DIR) / 'media' / 'shalom_profiles' / str(integracion.id)
    user_dir.mkdir(parents=True, exist_ok=True)
    ctx = playwright.chromium.launch_persistent_context(
        user_data_dir=str(user_dir),
        headless=True,
        slow_mo=random.randint(150, 350),
        args=['--disable-blink-features=AutomationControlled', '--no-sandbox'],
        user_agent=USER_AGENT,
        viewport={'width': 1366, 'height': 768},
        locale='es-PE',
        timezone_id='America/Lima',
    )
    ctx.add_init_script(_STEALTH_JS)
    # Timeouts amplios: rastrea.shalom es lento y networkidle no aplica
    ctx.set_default_navigation_timeout(60000)
    ctx.set_default_timeout(30000)
    return ctx


def ir_a(page, url):
    """Navega de forma robusta: 'commit' (no espera carga completa) + reintento.
    Evita los timeouts de páginas lentas/con conexiones persistentes."""
    for _ in range(2):
        try:
            page.goto(url, wait_until='commit', timeout=60000)
            esperar_carga(page)
            return True
        except Exception:
            espera_humana(2, 4)
    page.goto(url, wait_until='commit', timeout=60000)
    esperar_carga(page)
    return True


# ───────────────────────── Utilidades ─────────────────────────

_MESES = {
    'ene': 1, 'feb': 2, 'mar': 3, 'abr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'ago': 8, 'sep': 9, 'set': 9, 'oct': 10, 'nov': 11, 'dic': 12,
}


def parse_fecha(texto):
    """Intenta parsear la fecha del listado a date. Soporta dd/mm/yyyy y 'dd mmm yyyy'.
    Devuelve None si no puede."""
    if not texto:
        return None
    t = texto.strip().lower()
    for fmt in ('%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%d/%m/%y'):
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            pass
    # 'dd mmm yyyy' (ej. "10 jun 2026")
    partes = t.replace('.', '').split()
    if len(partes) >= 3 and partes[1][:3] in _MESES:
        try:
            return datetime(int(partes[2]), _MESES[partes[1][:3]], int(partes[0])).date()
        except (ValueError, KeyError):
            return None
    return None


# ───────────────────────── Etapa 1: listado ─────────────────────────

def _login_listado(page, sel, usuario, password, log=_noop):
    # Calentamiento: Google → home Shalom → login (referrer + cookies legítimas).
    log('Calentando navegación antes del login (Google → Shalom → login)…')
    _calentar(page, [sel.get('google_url'), sel.get('home_url'), sel['login_url']], log)
    espera_humana(1.5, 3)

    # Con contexto persistente puede que YA haya sesión: si no aparece el formulario
    # de login (o ya no estamos en /login), saltamos el login.
    hay_form = False
    try:
        page.wait_for_selector(sel['login_email_sel'], timeout=8000)
        hay_form = True
    except Exception:
        hay_form = page.locator(sel['login_email_sel']).count() > 0

    if not hay_form:
        log('Ya había sesión activa: no hace falta iniciar sesión.')
        return '/login' not in page.url  # ya estaba logueado

    log('Formulario de login detectado, ingresando credenciales despacio…')

    def _intento():
        movimiento_humano(page)
        _escribir_humano(page, sel['login_email_sel'], usuario, rapido=True, log=log, etiqueta='el usuario')
        _escribir_humano(page, sel['login_pass_sel'], password, log=log, etiqueta='la contraseña')   # lento
        try:
            page.check(sel['login_remember_sel'])
        except Exception:
            pass
        espera_humana(0.6, 1.3)
        log('Enviando el formulario de login…')
        page.click(sel['login_submit_sel'])
        # Esperar a salir de /login en vez de solo esperar carga.
        try:
            page.wait_for_function("() => !location.href.includes('/login')", timeout=20000)
        except Exception:
            esperar_carga(page)
        espera_humana(1.5, 2.5)
        ok = '/login' not in page.url
        log('Sesión iniciada ✓' if ok else 'Seguimos en /login tras enviar…')
        return ok

    if _intento():
        return True
    # Reintento único: a veces el primer tecleo no "prende" el formulario.
    log('Login no confirmado, reintentando con tecleo lento…')
    if page.locator(sel['login_email_sel']).count() == 0:
        return '/login' not in page.url
    return _intento()


def _extraer_filas(page, sel):
    filas = page.locator(sel['row_sel']).all()
    datos = []
    for fila in filas:
        try:
            estado = fila.locator(sel['row_status_sel']).first.inner_text().strip()
            orden = fila.locator(sel['row_orden_sel']).inner_text().strip()
            codigo = fila.locator(sel['row_codigo_sel']).inner_text().strip()
            cont = fila.locator(sel['row_contenido_sel']).all_inner_texts()
            recip = fila.locator(sel['row_recipient_sel']).all_inner_texts()
            deliv = fila.locator(sel['row_delivery_sel']).all_inner_texts()
            datos.append({
                'orden': orden, 'codigo': codigo, 'estado': estado,
                'producto': cont[0] if cont else '',
                'fecha': cont[1] if len(cont) > 1 else '',
                'nombre': recip[0] if recip else '',
                'dni': recip[1].replace('DNI:', '').strip() if len(recip) > 1 else '',
                'monto': fila.locator(sel['row_monto_sel']).inner_text().strip(),
                'lugar_entrega': deliv[0] if deliv else '',
                'tipo_envio': deliv[1] if len(deliv) > 1 else '',
            })
        except Exception:
            continue
    return datos


def importar_listado(page, sel, usuario, password, corte, max_paginas, on_pagina=None, log=_noop):
    """Recorre el listado paginado de pro.shalom.pe.
    `corte` = dict {orden, codigo, fecha(date|None)}: se detiene al alcanzarlo.

    También se detiene al llegar a la 'cola de entregados': si una página entera ya está
    ENTREGADA (en el estado del listado), de ahí hacia atrás todo está entregado, así que no
    se sigue bajando. Así 'Actualizar todo' no re-descarga lo antiguo ya entregado.
    Devuelve (lista_envios, alcanzo_corte)."""
    if not _login_listado(page, sel, usuario, password, log=log):
        raise RuntimeError('Login en pro.shalom.pe falló (revisa credenciales).')

    page.click(sel['menu_operaciones_sel'])
    espera_humana(0.8, 1.5)
    page.click(f"text={sel['menu_seguimiento_text']}")
    esperar_carga(page)
    espera_humana(2, 3)

    palabra_ent = (sel.get('palabra_entregado') or 'entregado').lower()
    todos = []
    alcanzo_corte = False
    pagina = 1
    while True:
        espera_humana(1, 2)
        filas = _extraer_filas(page, sel)
        if on_pagina:
            on_pagina(pagina, filas)

        # Corte: detener si llegamos al límite (de aquí hacia atrás todo entregado)
        pendientes_pagina = 0
        for f in filas:
            todos.append(f)
            if palabra_ent not in (f.get('estado', '') or '').lower():
                pendientes_pagina += 1
            if corte.get('orden') and f['orden'] == corte['orden'] and f['codigo'] == corte['codigo']:
                alcanzo_corte = True
                break
            fp = parse_fecha(f['fecha'])
            if corte.get('fecha') and fp and fp < corte['fecha']:
                alcanzo_corte = True
                break
        if alcanzo_corte:
            break

        # Parada por entrega: si en TODA la página no hubo ningún envío sin entregar,
        # de aquí hacia atrás todo está entregado → no seguimos descargando.
        if filas and pendientes_pagina == 0:
            alcanzo_corte = True
            log(f'Página {pagina} completa ya entregada: detengo la descarga (lo antiguo ya está entregado).')
            break

        if pagina >= max_paginas:
            break
        boton = page.locator(sel['next_btn_sel'])
        if boton.count() == 0 or not boton.is_enabled():
            break
        espera_humana(1.5, 3)
        boton.click()
        esperar_carga(page)
        espera_humana(1, 2)
        pagina += 1

    return todos, alcanzo_corte


# ───────────────────────── Etapa 2: validación ─────────────────────────

def _necesita_login_rastreo(page, sel):
    """Hay formulario de login si está el campo de contraseña (señal más fiable) o el de email."""
    try:
        if page.locator(sel['rastrea_pass_sel']).count() > 0:
            return True
        return page.locator(sel['rastrea_email_sel']).count() > 0
    except Exception:
        return False


def _rastrea_base(sel):
    """URL base del rastreo (la página de consulta, SIN /login). De aquí se cuelgan los
    detalles /rastrea/{orden}/{codigo}."""
    return (sel.get('rastrea_base_url')
            or sel.get('rastrea_url', '').replace('/login', '').rstrip('/'))


def _esperar_render_rastreo(page, sel, log=_noop, timeout=25000):
    """shalom.com.pe/rastrea es una SPA: el HTML inicial llega casi vacío y el contenido lo
    pinta el JS unos segundos después. Esperamos a que aparezca algo REAL (campos de login o
    del formulario de búsqueda, o el botón) antes de leer/capturar; si no, queda en blanco.
    Devuelve True si renderizó contenido."""
    try:
        page.wait_for_load_state('networkidle', timeout=timeout)
    except Exception:
        pass
    selectores = ', '.join(filter(None, [
        sel.get('rastrea_pass_sel'), sel.get('rastrea_email_sel'),
        sel.get('rastrea_orden_sel'), sel.get('rastrea_codigo_sel'),
        sel.get('rastrea_submit_sel'),
    ]))
    try:
        page.wait_for_selector(selectores, state='visible', timeout=timeout)
        espera_humana(0.6, 1.2)   # margen para animaciones de entrada
        return True
    except Exception:
        # Último recurso: esperar a que el body tenga algo de texto visible.
        try:
            page.wait_for_function(
                "() => document.body && document.body.innerText.trim().length > 40",
                timeout=8000)
            espera_humana(0.5, 1)
            return True
        except Exception:
            log('La página de rastreo no renderizó contenido (quedó en blanco).')
            return False


def asegurar_sesion_rastreo(page, sel, usuario, password, log=_noop, cap=_nocap):
    """Deja la sesión de rastreo lista, con el MISMO ingreso 'humano' que la etapa 1.

    Caso principal: entra Google → Shalom → /rastrea (NO directo) reutilizando la sesión
    ya guardada en el perfil; si ya está logueado, queda listo para consultar detalles.
    Caso alternativo: si /rastrea pide iniciar sesión, recién ahí hace login con tecleo lento
    y vuelve a /rastrea."""
    base = _rastrea_base(sel)
    # La "página de rastreo" es en realidad /rastrea/login (ahí está "Inicia sesión para
    # rastrear tu envío"). Entramos como humano vía Google → Shalom → /rastrea/login.
    log('Entrando al rastreo como humano (Google → Shalom → rastrea)…')
    _calentar(page, [sel.get('google_url'), sel.get('home_url'), sel['rastrea_url']], log)
    # CLAVE: es una SPA; ESPERAR a que el JS pinte el contenido o se ve en blanco.
    _esperar_render_rastreo(page, sel, log)
    movimiento_humano(page)
    cap(page, 'Llegué a la página de rastreo')
    if not _necesita_login_rastreo(page, sel):
        log('Sesión ya activa en rastreo: listo para consultar envíos.')
        cap(page, 'Sesión activa (sin pedir login)')
        return

    # Caso alternativo: hay que iniciar sesión.
    log('El rastreo pidió iniciar sesión → login con tecleo lento…')
    if '/login' not in (page.url or ''):
        ir_a(page, sel['rastrea_url'])
        _esperar_render_rastreo(page, sel, log)
    cap(page, 'Formulario de login del rastreo')

    def _intento():
        movimiento_humano(page)
        _escribir_humano(page, sel['rastrea_email_sel'], usuario, rapido=True, log=log, etiqueta='el usuario')
        _escribir_humano(page, sel['rastrea_pass_sel'], password, log=log, etiqueta='la contraseña')   # lento
        espera_humana(0.6, 1.2)
        log('Enviando el formulario de login…')
        page.click(sel['rastrea_submit_sel'])
        try:
            page.wait_for_selector(sel['rastrea_email_sel'], state='detached', timeout=15000)
        except Exception:
            esperar_carga(page)
        espera_humana(1.5, 2.5)
        ok = not _necesita_login_rastreo(page, sel)
        log('Sesión de rastreo iniciada ✓' if ok else 'El formulario de login sigue visible…')
        return ok

    if not _intento() and _necesita_login_rastreo(page, sel):
        log('Login de rastreo no confirmado, reintentando con tecleo lento…')
        _intento()
    # Ya logueado: si el formulario de búsqueda no está ya a la vista, ir a la página de
    # consulta y esperar a que renderice. (La SPA puede mostrar el buscador en la misma página.)
    if page.locator(sel['rastrea_orden_sel']).count() == 0:
        ir_a(page, base)
        _esperar_render_rastreo(page, sel, log)
    cap(page, 'Tras login, en la página de consulta')
    log('Listo para consultar envíos.')


def _diagnostico(page, log):
    """Vuelca qué hay en la página cuando NO se encontró el estado, para depurar."""
    try:
        titulo = page.title()
    except Exception:
        titulo = '?'
    try:
        cuerpo = page.inner_text('body')
        cuerpo = ' '.join(cuerpo.split())[:280]  # colapsa espacios/saltos
    except Exception:
        cuerpo = '(no se pudo leer el body)'
    log(f'  ↳ diagnóstico — título: "{titulo}" · texto visible: {cuerpo or "(vacío)"}')


def _leer_estado(page, estado_sel, fb_sel):
    """Espera a que el resultado renderice (carga por JS) y lee el estado.
    Imita a test2.py: espera 'networkidle' (que terminen las llamadas AJAX) y
    luego a que aparezca el elemento del estado."""
    try:
        page.wait_for_load_state('networkidle', timeout=15000)
    except Exception:
        pass
    try:
        page.wait_for_selector(f'{estado_sel}, {fb_sel}', timeout=12000)
    except Exception:
        espera_humana(1.5, 2.5)
    loc = page.locator(estado_sel).first
    if loc.count() == 0:
        loc = page.locator(fb_sel).first
    if loc.count() == 0:
        return None
    texto = loc.inner_text().strip()
    return texto or None


def _url_detalle(sel, orden, codigo):
    """URL directa del rastreo: https://shalom.com.pe/rastrea/{orden}/{codigo}."""
    plantilla = sel.get('rastrea_detalle_url', '')
    if plantilla:
        return plantilla.replace('{orden}', orden).replace('{codigo}', codigo)
    base = _rastrea_base(sel)
    return f'{base}/{orden}/{codigo}' if base else ''


# ─────────── Etapa 2 (método 'listado'): clic en la lupita ───────────

def abrir_seguimiento(page, sel, usuario, password, log=_noop):
    """Deja `page` logueada en pro.shalom.pe y en el listado 'Seguimiento de envíos'.

    Reutiliza la MISMA sesión/página donde el login SÍ funciona (la etapa 1). Si venimos
    de la etapa 1 ya estamos logueados; si la corrida es 'solo validar', inicia sesión."""
    necesita_login = (
        '/login' in (page.url or '')
        or 'shalom.pe' not in (page.url or '')
        or page.locator(sel['login_email_sel']).count() > 0
    )
    if necesita_login:
        if not _login_listado(page, sel, usuario, password, log=log):
            raise RuntimeError('Login en pro.shalom.pe falló (revisa credenciales).')

    # Asegurar que estamos en el listado de seguimiento (idempotente).
    try:
        page.click(sel['menu_operaciones_sel'])
        espera_humana(0.8, 1.5)
        page.click(f"text={sel['menu_seguimiento_text']}")
        esperar_carga(page)
        espera_humana(1.5, 2.5)
    except Exception:
        # Puede que ya estuviéramos en el listado (etapa 1 lo deja abierto).
        pass
    log('Listo para rastrear desde el listado (lupita).')


def _buscar_en_listado(page, sel, termino):
    """Escribe el término (orden o código) en el buscador del listado y espera el filtrado AJAX.
    Devuelve True si encontró el buscador."""
    buscador = page.locator(sel['seguimiento_buscar_sel']).first
    if buscador.count() == 0:
        return False
    buscador.click()
    espera_humana(0.2, 0.5)
    buscador.fill('')
    espera_humana(0.2, 0.4)
    buscador.press_sequentially(termino, delay=random.uniform(80, 160))
    espera_humana(1.4, 2.4)   # margen para que el listado filtre
    return True


def _login_rastreo_popup(page, sel, usuario, password, log=_noop):
    """Login en la pestaña de rastreo (mismo tecleo lento humano que la etapa 1)."""
    def _intento():
        movimiento_humano(page)
        _escribir_humano(page, sel['rastrea_email_sel'], usuario, rapido=True, log=log, etiqueta='el usuario')
        _escribir_humano(page, sel['rastrea_pass_sel'], password, log=log, etiqueta='la contraseña')   # lento
        espera_humana(0.6, 1.2)
        log('Enviando el formulario de login del rastreo…')
        page.click(sel['rastrea_submit_sel'])
        try:
            page.wait_for_selector(sel['rastrea_email_sel'], state='detached', timeout=15000)
        except Exception:
            esperar_carga(page)
        espera_humana(1.2, 2.0)
        return not _necesita_login_rastreo(page, sel)

    if not _intento() and _necesita_login_rastreo(page, sel):
        log('Login de rastreo no confirmado, reintentando…')
        _intento()


def validar_envio_listado(page, sel, orden, codigo, usuario, password, log=_noop, cap=_nocap):
    """Valida un envío SIN salir de pro.shalom.pe.

    Flujo: busca la fila por orden (o código) en el listado de seguimiento → clic en la lupita
    'Rastrea Pedido' → eso abre una PESTAÑA NUEVA al rastreo → ahí lee el estado. En esa pestaña
    maneja los 3 casos: (A) pide login, (B) pide orden+código, (C) muestra directo.
    Si no encuentra la fila/botón, propaga para que el runner reconecte y reintente."""
    estado_sel = sel['rastrea_estado_sel']
    fb_sel = sel['rastrea_estado_sel_fallback']

    # 1) Filtrar el listado para traer la fila a la vista y ubicar la lupita.
    _buscar_en_listado(page, sel, orden)
    boton = page.locator(sel['seguimiento_track_btn_sel']).first
    try:
        boton.wait_for(state='visible', timeout=8000)
    except Exception:
        _buscar_en_listado(page, sel, codigo)   # reintento por código
        boton = page.locator(sel['seguimiento_track_btn_sel']).first
        if boton.count() == 0:
            log(f'⚠ No encontré la fila/lupita de {orden}/{codigo} en el listado.')
            cap(page, f'SIN fila/lupita ({orden}/{codigo})')
            _diagnostico(page, log)
            return None

    # 2) Clic en la lupita → debería abrir una pestaña nueva.
    log(f'Clic en la lupita (Rastrea Pedido) de {orden}/{codigo}…')
    ctx = page.context
    try:
        with ctx.expect_page(timeout=15000) as pop_info:
            boton.click()
        popup = pop_info.value
    except Exception:
        # No abrió pestaña nueva: tal vez navegó en la misma o abrió un modal inline.
        popup = page

    es_popup = popup is not page
    try:
        _esperar_render_rastreo(popup, sel, log)
        movimiento_humano(popup)
        cap(popup, f'Rastreo abierto ({orden}/{codigo})')

        # Caso A: la pestaña pide iniciar sesión.
        if _necesita_login_rastreo(popup, sel):
            log('La pestaña de rastreo pidió login → ingresando…')
            _login_rastreo_popup(popup, sel, usuario, password, log=log)
            _esperar_render_rastreo(popup, sel, log)
            cap(popup, f'Tras login en rastreo ({orden}/{codigo})')

        # Caso B: la pestaña pide orden + código (formulario, sin estado todavía).
        pide_form = (popup.locator(sel['rastrea_orden_sel']).count() > 0
                     and _leer_estado(popup, estado_sel, fb_sel) is None)
        if pide_form:
            log(f'La pestaña pide orden y código → escribiendo {orden}/{codigo}…')
            _escribir_humano(popup, sel['rastrea_orden_sel'], orden, rapido=True)
            espera_humana(0.4, 0.9)
            _escribir_humano(popup, sel['rastrea_codigo_sel'], codigo, rapido=True)
            movimiento_humano(popup)
            cap(popup, f'Datos escritos ({orden}/{codigo})')
            popup.click(sel['rastrea_submit_sel'])
            esperar_carga(popup)

        # Caso C (o tras A/B): leer el estado.
        texto = _leer_estado(popup, estado_sel, fb_sel)
        cap(popup, f'Resultado {orden}/{codigo}: {texto or "(sin estado)"}')
        if not texto:
            log(f'⚠ No se encontró el estado. Página: {popup.url}')
            _diagnostico(popup, log)
        return texto
    finally:
        # Cerrar la pestaña del rastreo para no acumular pestañas; la del listado queda viva.
        if es_popup:
            try:
                popup.close()
            except Exception:
                pass


def validar_envio(page, sel, orden, codigo, log=_noop, cap=_nocap):
    """Devuelve el estado real de un envío (o None).

    Método principal: FORMULARIO de búsqueda (escribe orden y código en los dos campos).
    Quedarse en /rastrea y buscar por el formulario no recarga la página (consulta AJAX),
    así no se dispara el anti-bot que SÍ se activaba al navegar a la URL directa del detalle.

    Método oculto (usar_url_directa=True, OFF por defecto): URL directa /rastrea/{orden}/{codigo}."""
    estado_sel = sel['rastrea_estado_sel']
    fb_sel = sel['rastrea_estado_sel_fallback']

    # ── Método oculto: URL directa (solo si se activa a propósito) ──
    if sel.get('usar_url_directa'):
        url = _url_detalle(sel, orden, codigo)
        if url:
            log(f'Abriendo URL directa: {url}')
            try:
                ir_a(page, url)
                if _necesita_login_rastreo(page, sel):
                    raise RuntimeError('La sesión de rastreo se cayó (el detalle pidió login).')
                texto = _leer_estado(page, estado_sel, fb_sel)
                if texto:
                    log(f'Estado leído (URL directa): {texto}')
                    return texto
                log(f'URL directa sin estado (página: {page.url}). Probando formulario…')
                _diagnostico(page, log)
            except RuntimeError:
                raise
            except Exception as e:
                log(f'URL directa falló ({type(e).__name__}). Probando formulario…')

    # ── Método principal: formulario de búsqueda (dos campos) ──
    # Solo volvemos a /rastrea si el formulario no está a la vista (evita recargas inútiles).
    in_orden = page.locator(sel['rastrea_orden_sel'])
    if in_orden.count() == 0 or _necesita_login_rastreo(page, sel):
        try:
            ir_a(page, _rastrea_base(sel))
        except Exception:
            pass
        _esperar_render_rastreo(page, sel, log)   # esperar a que la SPA pinte el formulario
        movimiento_humano(page)
        in_orden = page.locator(sel['rastrea_orden_sel'])

    # Si la página pide login, la sesión se cayó: propagamos para que el runner reconecte.
    if _necesita_login_rastreo(page, sel):
        raise RuntimeError('La sesión de rastreo se cayó (pidió login).')
    if in_orden.count() == 0:
        log(f'⚠ No se encontró el formulario de búsqueda (página: {page.url}).')
        cap(page, f'SIN formulario de búsqueda ({orden}/{codigo})')
        _diagnostico(page, log)
        return None

    log(f'Escribiendo orden {orden} y código {codigo} en los dos campos…')
    _escribir_humano(page, sel['rastrea_orden_sel'], orden, rapido=True)
    espera_humana(0.4, 0.9)
    _escribir_humano(page, sel['rastrea_codigo_sel'], codigo, rapido=True)
    movimiento_humano(page)
    cap(page, f'Datos escritos ({orden}/{codigo})')
    log('Enviando consulta y esperando resultado…')
    page.click(sel['rastrea_submit_sel'])
    esperar_carga(page)
    texto = _leer_estado(page, estado_sel, fb_sel)
    cap(page, f'Resultado {orden}/{codigo}: {texto or "(sin estado)"}')
    if not texto:
        log(f'⚠ No se encontró el estado (formulario). Página final: {page.url}')
        _diagnostico(page, log)
    return texto
