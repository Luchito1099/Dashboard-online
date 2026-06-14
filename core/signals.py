# core/signals.py
"""Señal que asegura que CADA usuario tenga un Perfil asociado.
Cuando se crea un User, se genera su Perfil automáticamente:
  - superuser  → rol='admin'
  - resto      → rol='vendedor'
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User

from .models import Perfil


@receiver(post_save, sender=User)
def crear_perfil_usuario(sender, instance, created, **kwargs):
    # Solo al crear el usuario por primera vez
    if not created:
        return

    # El rol depende de si es superusuario
    rol = 'admin' if instance.is_superuser else 'vendedor'

    # get_or_create evita duplicados si la señal se disparara dos veces
    Perfil.objects.get_or_create(usuario=instance, defaults={'rol': rol})
