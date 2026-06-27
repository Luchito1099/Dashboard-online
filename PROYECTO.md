# PROYECTO Dashboard — Hoja de contexto

> Pega este archivo en futuras conversaciones en vez de todo el proyecto.
> Última actualización: 2026-06-14.

## Stack
- Django 6.0.6, Python 3.14, **SQLite en local / PostgreSQL en producción** (switch automático).
- HTML/CSS/JS **vanilla** (sin React ni librerías). Whitenoise para estáticos.
- Auth Django nativo. Locale `es-pe`, zona `America/Lima`, `USE_TZ=True`.
- Despliegue: **Coolify** (VPS Hetzner) con Docker + Gunicorn + PostgreSQL.
- **Windows local**: la consola es cp1252 → al correr management commands con emojis usar
  `PYTHONIOENCODING=utf-8` (PowerShell: `$env:PYTHONIOENCODING="utf-8"`).

## Estructura
```
DASHBOARD-ONLINE/
├── config/            settings.py (env vars), urls.py (core, capacitacion, productos, herramientas)
├── core/              login, home, perfil, configuración, buscador
│   ├── models.py      Perfil, ConfiguracionSistema
│   ├── views.py       home, login_view, logout_view, configuracion, api_buscar
│   ├── signals.py     post_save User → crea Perfil (superuser→admin, resto→vendedor)
│   ├── context_processors.py  runbook → rb_done/rb_total/rb_proxima/puede_editar
│   └── static/core/
│       ├── css/  base.css, login.css, capacitacion.css, admin_cap.css,
│       │         productos.css, configuracion.css, herramientas.css
│       └── js/   base.js (NO TOCAR), extras.js (buscador + link Configuración + compartir)
├── capacitacion/      runbook diario (Tarea, Bloque, BloqueTarea, ProgresoTarea)
│   └── management/commands/  seed_capacitacion.py, crear_vendedor.py
├── productos/         catálogo
│   ├── models.py      Producto, ImagenProducto, ObjecionProducto, LinkProducto, MediaProducto
│   └── management/commands/  seed_productos.py
├── herramientas/      enlaces a herramientas externas
│   ├── models.py      HerramientaExterna
│   └── management/commands/  seed_herramientas.py
├── templates/
│   ├── base.html               ⚠️ NO TOCAR (sidebar, topbar, panel derecho)
│   ├── registration/login.html ⚠️ NO TOCAR
│   ├── core/home.html, core/configuracion.html
│   ├── capacitacion/index.html, capacitacion/admin.html
│   ├── productos/catalogo.html, ficha_rapida.html, admin.html
│   └── herramientas/lista.html, _tarjeta.html, admin.html
├── Dockerfile, entrypoint.sh, requirements.txt, .env.example, .gitignore
└── manage.py
```

## Modelos

### core
- **Perfil**: `usuario`(OneToOne), `rol`(admin|vendedor, default vendedor), `activo`. Métodos `es_admin()`, `es_vendedor()`.
- **ConfiguracionSistema** (singleton pk=1): `vendedor_puede_editar_videos`(True), `vendedor_puede_ver_productos`(True). Acceso: `ConfiguracionSistema.get_solo()`.

### capacitacion
- **Tarea**: orden, hora("08:00"), mins, tipo(LLAMADA|PEDIDO|SEGUIM|REPORTE|TURNO), prioridad(alta|media|baja), flexible, nombre, habilidades(JSON), descripcion, pasos(JSON), tips(JSON [{k,t}] k=tip|warn|info), titulo_video, activo.
- **Bloque**: label, tareas(M2M through BloqueTarea), orden.
- **BloqueTarea**: bloque(FK related_name=`bloquearea_set`), tarea(FK), orden.
- **ProgresoTarea**: usuario(FK related_name=`progreso_set`), tarea(FK), completada, fecha(auto). Unique: usuario+tarea+fecha.

### productos
- **Producto**: nombre, sku, categoria, orden, activo, `precio`(Decimal), `precio_oferta`(Decimal null), `en_oferta`(bool), descripcion, caracteristicas(JSON), imagen_url, video_url, **link_pago**(URL). Props `precio_mostrar`, `tiene_oferta`. (Ya NO existe `link_web` → ahora es LinkProducto.)
- **ImagenProducto**: producto(FK related_name=`imagenes`), url, orden.
- **ObjecionProducto**: producto(FK related_name=`objeciones`), objecion(Text), respuesta(Text), orden.
- **LinkProducto**: producto(FK related_name=`links`), titulo, url, orden.  ← múltiples enlaces web.
- **MediaProducto**: producto(FK related_name=`medios`), tipo(imagen|video), url, titulo, orden.  ← material compartible.

### herramientas
- **HerramientaExterna**: nombre, descripcion, url, icono(emoji), categoria, activo, orden.

## URLs
| Ruta | Nombre | Acceso |
|---|---|---|
| `/` | core:home | login |
| `/login/` `/logout/` | core:login / logout | público / login |
| `/configuracion/` | core:configuracion | **admin** |
| `/buscar/?q=` | core:buscar (JSON {tareas,productos}) | login |
| `/capacitacion/` | capacitacion:index | login |
| `/capacitacion/toggle/<id>/` | capacitacion:toggle_tarea (POST JSON) | login |
| `/capacitacion/editar/<id>/`, `/capacitacion/admin/` | capacitacion:editar_tarea / admin_panel | **admin** |
| `/productos/` | productos:catalogo | login* |
| `/productos/<id>/` | productos:detalle | login* |
| `/productos/ficha/<id>/` | productos:ficha_rapida | login* |
| `/productos/admin/`, `/crear/`, `/editar/<id>/`, `/eliminar/<id>/` | productos:* (POST) | **admin** |
| `/herramientas/` | herramientas:lista | login |
| `/herramientas/admin/`, `/crear/`, `/editar/<id>/`, `/eliminar/<id>/` | herramientas:* (POST) | **admin** |

\* productos requiere además `ConfiguracionSistema.vendedor_puede_ver_productos` para vendedores.

## Permisos
- `@login_required` en todas las vistas.
- Helper **único**: `capacitacion.views.es_admin(user)` → superuser o `perfil.rol=='admin'`. Importarlo, no duplicarlo.
- Vendedor en rutas admin → `redirect` con `messages.error`.
- **Vendedor**: runbook (marca/simula/videos), catálogo+fichas (si config), herramientas.
- **Admin**: todo + editar tareas, administrar productos/herramientas, gestionar usuarios/config.

## Frontend / convenciones
- `{% extends 'base.html' %}` 1ª línea, `{% load static %}` después. JS vanilla inline en `{% block extra_js %}`.
- Bloques base.html: `title, extra_css, breadcrumb, content, right_panel, extra_js, nav_home, nav_capacitacion, nav_config`.
- `extras.js`: buscador topbar + reescribe link Configuración (base.html lo tiene en `#`) + helpers globales `compartirWhatsApp(url)` y `copiarLinkMedio(btn,url)`.
- **Selector central** (3 pills): Capacitación / Productos / Herramientas. Navegación entre `/capacitacion/`, `/productos/`, `/herramientas/`; recuerda `localStorage.dash_view`. base.html es NO TOCAR, por eso no hay item en el sidebar.
- Runbook: layout especial `body:has(.cap-layout) .page-content {overflow:hidden}`. Resto = scroll natural.
- **Compartir a WhatsApp**: `https://wa.me/?text={encodeURIComponent(url)}`.
- **Video (fix Error 153)**: `parseVideoUrl` → `https://www.youtube.com/embed/<id>?rel=0` o `player.vimeo.com/video/<id>`. iframe con `allow="...; web-share"` + `referrerpolicy="strict-origin-when-cross-origin"`.
- Videos de tareas: localStorage `dash_vid_<tarea_id>`.

## Variables CSS (base.css)
```
--primary:oklch(62% 0.18 195)  --primary-dark:oklch(52% 0.18 195)  --primary-bg:oklch(62% 0.18 195 /0.08)
--bg:#f4f7fb  --surface:#fff  --border:#e8eef6  --border-dark:#d0dbe8
--text:#0d1e2e  --text-secondary:#3a5470  --muted:#7a9ab8  --sidebar-bg:#0d1f33
--success:oklch(58% 0.18 145)  --error:oklch(60% 0.2 25)  --radius:10px  --shadow  --shadow-md
```
- Prioridad: alta=#ef4444, media=#f59e0b, baja=#22c55e. WhatsApp=#25d366.

## Usuarios de prueba
- **admin** — superusuario, Perfil rol=admin.
- **vendedor1 / vendedor123** — rol vendedor.
- Cada usuario nuevo recibe Perfil automático vía señal.

## Comandos
```bash
python manage.py makemigrations && python manage.py migrate
python manage.py seed_capacitacion   # 13 tareas + 4 bloques
python manage.py crear_vendedor      # vendedor1/vendedor123 + Perfil admin a superusuarios
python manage.py seed_productos      # 4 productos (objeciones, links, medios)
python manage.py seed_herramientas   # 6 herramientas externas
# Windows: anteponer  $env:PYTHONIOENCODING="utf-8"
```

## Producción (Coolify + PostgreSQL)
- `settings.py` lee de env: `SECRET_KEY, DEBUG, ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS, DB_*`.
  Si existe `DB_HOST` → PostgreSQL; si no → SQLite. Con `DEBUG=False` activa cookies seguras + `SECURE_PROXY_SSL_HEADER`.
- `Dockerfile` (python:3.12-slim) instala requirements, corre `collectstatic`, y arranca con `entrypoint.sh`
  (que ejecuta `migrate` y luego `gunicorn config.wsgi:application`).
- Variables en `.env.example`. Estáticos vía Whitenoise (CompressedManifest).

## NO TOCAR
base.html, base.css, base.js, login.css, login/perfil, seed_capacitacion.py.
