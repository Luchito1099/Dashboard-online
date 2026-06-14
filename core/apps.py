# core/apps.py
from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        # Importa las señales para que queden registradas al arrancar la app
        from . import signals  # noqa: F401
