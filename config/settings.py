# config/settings.py
from pathlib import Path
import os

# python-dotenv: carga un archivo .env en local si está disponible (en producción
# las variables las inyecta Coolify directamente, así que el import es opcional).
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent

# ── Seguridad / entorno (todo configurable por variables de entorno) ──
SECRET_KEY = os.environ.get(
    'SECRET_KEY',
    'django-insecure-s@8*ykm8l89e#ja(*$j6-$b=yv%j%k0=qozzp2w+z1bx)(g-1x'  # solo para local
)

# DEBUG=True en local; en producción se pone DEBUG=False por variable de entorno
DEBUG = os.environ.get('DEBUG', 'True') == 'True'

# Hosts permitidos separados por coma: "dashboard.conluismz.com,www..."
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '*').split(',')

# Orígenes de confianza para CSRF (deben incluir el esquema https://)
_csrf = os.environ.get('CSRF_TRUSTED_ORIGINS', '')
CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf.split(',') if o.strip()]

# Clave Fernet para cifrar credenciales de integraciones. Si está vacía, el módulo
# integraciones la deriva del SECRET_KEY (ver integraciones/crypto.py).
INTEGRACIONES_FERNET_KEY = os.environ.get('INTEGRACIONES_FERNET_KEY', '')

INSTALLED_APPS = [
    'core',
    'capacitacion',
    'productos',
    'herramientas',
    'integraciones',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.runbook',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# ── Base de datos: PostgreSQL si hay DB_HOST (producción), si no SQLite (local) ──
if os.environ.get('DB_HOST'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('DB_NAME'),
            'USER': os.environ.get('DB_USER'),
            'PASSWORD': os.environ.get('DB_PASSWORD'),
            'HOST': os.environ.get('DB_HOST'),
            'PORT': os.environ.get('DB_PORT', '5432'),
            # Conexiones persistentes: reutiliza la conexión hasta 600s en vez de
            # abrir una nueva en cada request (gran parte de los ~3.5s por pestaña).
            'CONN_MAX_AGE': 600,
            'OPTIONS': {
                # Si la DB no responde el handshake en 3s, fallar rápido en vez
                # de dejar el request colgado.
                'connect_timeout': 3,
            },
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# ── Caché en memoria del proceso (sin Redis por ahora) ──
# Ojo: LocMemCache es por proceso; con varios workers de Gunicorn cada uno
# tiene su propia caché (no se comparte). Suficiente para sesiones cacheadas.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# Sesiones en BD (la tabla django_session ya existe vía migraciones).
SESSION_ENGINE = 'django.contrib.sessions.backends.db'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'es-pe'
TIME_ZONE = 'America/Lima'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# ── Ajustes de seguridad que solo aplican en producción (DEBUG=False) ──
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')  # detrás del proxy de Coolify
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# ── Hashers de contraseña ──
# Solo PBKDF2 por ahora (Argon2 requería el paquete argon2-cffi, que no está
# instalado). Cuando lo añadas a requirements.txt podrás anteponer Argon2.
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
]

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
