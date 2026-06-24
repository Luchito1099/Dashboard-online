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

def _login_listado(page, sel, usuario, password):
    ir_a(page, sel['login_url'])
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
        return '/login' not in page.url  # ya estaba logueado

    page.fill(sel['login_email_sel'], usuario)
    espera_humana(0.5, 1.2)
    page.fill(sel['login_pass_sel'], password)
    espera_humana(0.5, 1.2)
    try:
        page.check(sel['login_remember_sel'])
    except Exception:
        pass
    espera_humana(0.5, 1)
    page.click(sel['login_submit_sel'])
    esperar_carga(page)
    espera_humana(2, 3)
    return '/login' not in page.url


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


def importar_listado(page, sel, usuario, password, corte, max_paginas, on_pagina=None):
    """Recorre el listado paginado de pro.shalom.pe.
    `corte` = dict {orden, codigo, fecha(date|None)}: se detiene al alcanzarlo.
    Devuelve (lista_envios, alcanzo_corte)."""
    if not _login_listado(page, sel, usuario, password):
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


def _noop(_):
    pass


def asegurar_sesion_rastreo(page, sel, usuario, password, log=_noop):
    log('Conectando a la página de rastreo…')
    ir_a(page, sel['rastrea_url'])
    espera_humana(1, 2)
    movimiento_humano(page)
    if _necesita_login_rastreo(page, sel):
        log('Sesión no activa → iniciando sesión…')
        page.fill(sel['rastrea_email_sel'], usuario)
        espera_humana(0.5, 1)
        page.fill(sel['rastrea_pass_sel'], password)
        espera_humana(0.5, 1)
        page.click(sel['rastrea_submit_sel'])
        esperar_carga(page)
        espera_humana(1.5, 2.5)
        log('Login enviado, formulario de búsqueda listo.')
    else:
        log('Sesión ya activa, formulario de búsqueda listo.')


def _leer_estado(page, estado_sel, fb_sel, log):
    """Espera a que el resultado renderice (carga por JS) y lee el estado."""
    try:
        page.wait_for_selector(f'{estado_sel}, {fb_sel}', timeout=12000, state='visible')
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
            texto = _leer_estado(page, estado_sel, fb_sel, log)
            if texto:
                log(f'Estado leído (URL directa): {texto}')
                return texto
            log(f'URL directa sin estado (página: {page.url}). Probando formulario…')
        except Exception as e:
            log(f'URL directa falló ({type(e).__name__}). Probando formulario…')

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
    texto = _leer_estado(page, estado_sel, fb_sel, log)
    if not texto:
        log(f'⚠ No se encontró el estado (formulario). Página final: {page.url}')
    return texto
