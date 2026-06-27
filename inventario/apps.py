# inventario/apps.py
from django.apps import AppConfig


class InventarioConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'inventario'
    verbose_name = 'Inventario'

    def ready(self):
        # Conecta la señal que ajusta el stock al entregar/revertir un pedido
        from . import signals  # noqa: F401
