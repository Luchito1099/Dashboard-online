# capacitacion/management/commands/crear_vendedor.py
"""Comando de utilidad para pruebas de permisos:
  - Crea el usuario de prueba  vendedor1 / vendedor123  con Perfil rol='vendedor'.
  - Asegura que TODOS los superusuarios existentes tengan Perfil rol='admin'
    (la señal post_save solo crea el Perfil de usuarios nuevos, no de los anteriores).

Uso:  python manage.py crear_vendedor
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

from core.models import Perfil


class Command(BaseCommand):
    help = 'Crea un usuario vendedor de prueba y asegura el Perfil de los superusuarios.'

    def handle(self, *args, **options):
        # ── 1. Usuario vendedor de prueba ──
        vendedor, creado = User.objects.get_or_create(
            username='vendedor1',
            defaults={'first_name': 'Vendedor', 'last_name': 'Demo'},
        )
        if creado:
            vendedor.set_password('vendedor123')
            vendedor.save()
            self.stdout.write(self.style.SUCCESS('Usuario vendedor1 creado (password: vendedor123).'))
        else:
            self.stdout.write('El usuario vendedor1 ya existía.')

        # Aseguramos su Perfil como vendedor
        perfil, _ = Perfil.objects.get_or_create(
            usuario=vendedor, defaults={'rol': 'vendedor'}
        )
        if perfil.rol != 'vendedor':
            perfil.rol = 'vendedor'
            perfil.save()
        self.stdout.write('Perfil de vendedor1 → rol="vendedor".')

        # ── 2. Backfill: cada superusuario debe tener Perfil admin ──
        for admin in User.objects.filter(is_superuser=True):
            perfil_admin, _ = Perfil.objects.get_or_create(
                usuario=admin, defaults={'rol': 'admin'}
            )
            if perfil_admin.rol != 'admin':
                perfil_admin.rol = 'admin'
                perfil_admin.save()
            self.stdout.write(f'Perfil de {admin.username} → rol="admin".')

        self.stdout.write(self.style.SUCCESS('\nListo. Permisos de prueba configurados.'))
