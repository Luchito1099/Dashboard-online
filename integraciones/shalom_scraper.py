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
    Devuelve (lista_envios, alcanzo_corte)."""
    if not _login_listado(page, sel, usuario, password, log=log):
        raise RuntimeError('Login en pro.shalom.pe falló (revisa credenciales).')

    page.click(sel['menu_operaciones_sel'])
    espera_humana(0.8, 1.5)
    page.click(f"text={sel['menu_seguimiento_text']}")
    esperar_carga(page)
    espera_humana(2, 3)

    todos = []
    alcanzo_corte = False
    pagina = 1
    while True:
        espera_humana(1, 2)
        filas = _extraer_filas(page, sel)
        if on_pagina:
            on_pagina(pagina, filas)

        # Corte: detener si llegamos al límite (de aquí hacia atrás todo entregado)
        for f in filas:
            todos.append(f)
            if corte.get('orden') and f['orden'] == corte['orden'] and f['codigo'] == corte['codigo']:
                alcanzo_corte = True
                break
            fp = parse_fecha(f['fecha'])
            if corte.get('fecha') and fp and fp < corte['fecha']:
                alcanzo_corte = True
                break
        if alcanzo_corte:
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
    return page.locator(sel['rastrea_email_sel']).count() > 0


def asegurar_sesion_rastreo(page, sel, usuario, password, log=_noop):
    log('Conectando a la página de rastreo…')
    ir_a(page, sel['rastrea_url'])
    espera_humana(1, 2)
    movimiento_humano(page)
    if not _necesita_login_rastreo(page, sel):
        log('Sesión ya activa, formulario de búsqueda listo.')
        return

    log('No hay sesión → calentando navegación (Google → Shalom → login)…')
    # Calentamiento: Google → home Shalom → login de rastreo.
    _calentar(page, [sel.get('google_url'), sel.get('home_url'), sel['rastrea_url']], log)
    log('Formulario de login detectado, ingresando credenciales despacio…')

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
    log('Formulario de búsqueda listo.')


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
    base = sel.get('rastrea_url', '').replace('/login', '').rstrip('/')
    return f'{base}/{orden}/{codigo}' if base else ''


def validar_envio(page, sel, orden, codigo, log=_noop):
    """Devuelve el estado real de un envío (o None).
    Método 1 (principal): URL directa /rastrea/{orden}/{codigo}.
    Método 2 (respaldo): formulario de búsqueda."""
    estado_sel = sel['rastrea_estado_sel']
    fb_sel = sel['rastrea_estado_sel_fallback']

    # ── Método 1: URL directa ──
    url = _url_detalle(sel, orden, codigo)
    if url:
        log(f'Abriendo URL directa: {url}')
        try:
            ir_a(page, url)
            texto = _leer_estado(page, estado_sel, fb_sel)
            if texto:
                log(f'Estado leído (URL directa): {texto}')
                return texto
            log(f'URL directa sin estado (página: {page.url}). Probando formulario…')
            _diagnostico(page, log)
        except Exception as e:
            log(f'URL directa falló ({type(e).__name__}: {e}). Probando formulario…')

    # ── Método 2: formulario de búsqueda ──
    try:
        ir_a(page, sel.get('rastrea_url', '').replace('/login', '').rstrip('/'))
    except Exception:
        pass
    movimiento_humano(page)
    in_orden = page.locator(sel['rastrea_orden_sel'])
    in_codigo = page.locator(sel['rastrea_codigo_sel'])
    if in_orden.count() == 0:
        log(f'⚠ No se encontró el formulario de búsqueda (página: {page.url}).')
        _diagnostico(page, log)
        return None
    log(f'Escribiendo orden {orden} y código {codigo} en el formulario…')
    in_orden.first.click(); espera_humana(0.3, 0.6)
    in_orden.first.fill(''); in_orden.first.fill(orden); espera_humana(0.5, 1)
    in_codigo.first.click(); espera_humana(0.3, 0.6)
    in_codigo.first.fill(''); in_codigo.first.fill(codigo); espera_humana(0.5, 1)
    movimiento_humano(page)
    log('Enviando consulta y esperando resultado…')
    page.click(sel['rastrea_submit_sel'])
    esperar_carga(page)
    texto = _leer_estado(page, estado_sel, fb_sel)
    if not texto:
        log(f'⚠ No se encontró el estado (formulario). Página final: {page.url}')
        _diagnostico(page, log)
    return texto
