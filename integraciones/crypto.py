# integraciones/crypto.py
"""Cifrado simétrico de credenciales (tokens / API keys) para guardarlas en BD
sin dejarlas en texto plano.

Clave de cifrado:
  1. Si existe la variable de entorno INTEGRACIONES_FERNET_KEY, se usa esa
     (clave Fernet válida: 32 bytes base64 url-safe).
  2. Si no, en local se deriva una clave ESTABLE desde settings.SECRET_KEY.
     Suficiente para desarrollo; en producción se debe definir la env var.
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


def _obtener_clave():
    """Devuelve una clave Fernet válida (bytes) desde la env var o derivada del SECRET_KEY."""
    clave_env = getattr(settings, 'INTEGRACIONES_FERNET_KEY', None)
    if clave_env:
        return clave_env.encode() if isinstance(clave_env, str) else clave_env
    # Derivación estable desde SECRET_KEY: sha256 → 32 bytes → base64 url-safe.
    digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return base64.urlsafe_b64encode(digest)


_fernet = Fernet(_obtener_clave())


def cifrar(texto):
    """Cifra un string. Devuelve '' si la entrada es vacía/None."""
    if not texto:
        return ''
    return _fernet.encrypt(texto.encode()).decode()


def descifrar(token):
    """Descifra un string cifrado. Devuelve '' si está vacío o no se puede descifrar
    (p. ej. valor antiguo en texto plano o clave cambiada)."""
    if not token:
        return ''
    try:
        return _fernet.decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return ''


class EncryptedTextField(models.TextField):
    """TextField que cifra su valor al guardar en BD y lo descifra al leer.
    Las vistas y plantillas trabajan siempre con el texto plano."""

    def get_prep_value(self, value):
        """Valor que va a la BD → cifrado."""
        value = super().get_prep_value(value)
        return cifrar(value)

    def from_db_value(self, value, expression, connection):
        """Valor que viene de la BD → descifrado."""
        return descifrar(value)
