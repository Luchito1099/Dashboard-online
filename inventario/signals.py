# inventario/signals.py
"""Ajusta el stock automáticamente cuando un pedido cambia de estado (entregado/revertido).
Se conecta en apps.py. Es defensivo: si algo falla, NO rompe el guardado del pedido."""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from integraciones.models import Pedido

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Pedido)
def pedido_guardado(sender, instance, created, **kwargs):
    # Al crear, el pedido nace en 'creado' → no hay nada que descontar.
    if created:
        return
    try:
        from .services import sincronizar_stock_pedido
        sincronizar_stock_pedido(instance)
    except Exception:
        logger.exception('inventario: no se pudo sincronizar el stock del pedido %s', instance.pk)
