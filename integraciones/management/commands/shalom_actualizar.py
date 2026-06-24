# integraciones/management/commands/shalom_actualizar.py
"""Corre una actualización de Shalom (etapa 1 + etapa 2) para una integración.

Ejemplos:
  python manage.py shalom_actualizar --integracion 3 --manual
  python manage.py shalom_actualizar --integracion 3 --solo-importar
  python manage.py shalom_actualizar --integracion 3 --orden 12345678 --codigo 1234
"""
from django.core.management.base import BaseCommand, CommandError

from integraciones.models import Integracion
from integraciones import shalom_runner


class Command(BaseCommand):
    help = 'Actualiza envíos de una integración Shalom (importa y/o valida).'

    def add_arguments(self, parser):
        parser.add_argument('--integracion', type=int, required=True)
        parser.add_argument('--manual', action='store_true')
        parser.add_argument('--solo-importar', action='store_true')
        parser.add_argument('--solo-validar', action='store_true')
        parser.add_argument('--orden', type=str, default=None)
        parser.add_argument('--codigo', type=str, default=None)

    def handle(self, *args, **opts):
        try:
            integ = Integracion.objects.get(id=opts['integracion'], proveedor='shalom')
        except Integracion.DoesNotExist:
            raise CommandError('No existe una integración Shalom con ese id.')

        solo = None
        if opts['solo_importar']:
            solo = 'importar'
        elif opts['solo_validar']:
            solo = 'validar'

        tipo = 'manual' if opts['manual'] else 'auto'
        self.stdout.write(f'Corriendo Shalom para «{integ.nombre}» (solo={solo})…')
        ok, msg = shalom_runner.correr(
            integ, tipo=tipo, solo=solo, orden=opts['orden'], codigo=opts['codigo']
        )
        estilo = self.style.SUCCESS if ok else self.style.ERROR
        self.stdout.write(estilo(msg))
