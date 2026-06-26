# anuncios/management/commands/sincronizar_ads.py
"""Extrae los insights de Meta para todas las cuentas activas con token, directamente
desde la Graph API. Programar en cron (ej. cada hora o 1-2 veces al día).

    python manage.py sincronizar_ads
    python manage.py sincronizar_ads --dias 7
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from anuncios import connectors
from anuncios.models import CuentaPublicitaria


class Command(BaseCommand):
    help = 'Sincroniza insights de Meta Ads (Graph API) para las cuentas activas con token.'

    def add_arguments(self, parser):
        parser.add_argument('--dias', type=int, default=30, help='Días hacia atrás a extraer.')

    def handle(self, *args, **opts):
        dias = opts['dias']
        cuentas = CuentaPublicitaria.objects.filter(activo=True).exclude(access_token='')
        if not cuentas:
            self.stdout.write('No hay cuentas activas con token.')
            return
        for cuenta in cuentas:
            ok, msg, _ = connectors.sincronizar(cuenta, dias=dias)
            cuenta.ultimo_sync_ok = ok
            cuenta.ultimo_sync_msg = msg[:255]
            cuenta.ultimo_sync_en = timezone.now()
            cuenta.save(update_fields=['ultimo_sync_ok', 'ultimo_sync_msg', 'ultimo_sync_en'])
            estilo = self.style.SUCCESS if ok else self.style.ERROR
            self.stdout.write(estilo(f'{cuenta.nombre}: {msg}'))
