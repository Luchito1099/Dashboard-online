# anuncios/management/commands/alertas_ads.py
"""Evalúa el CPA real por anuncio y dispara alertas a n8n (Telegram) cuando supera el
umbral configurado durante N días consecutivos. Programar en cron o llamar desde n8n.

    python manage.py alertas_ads
"""
from django.core.management.base import BaseCommand

from anuncios.services import evaluar_alertas


class Command(BaseCommand):
    help = 'Evalúa el CPA real y envía alertas a n8n cuando supera el umbral configurado.'

    def handle(self, *args, **opts):
        enviadas = evaluar_alertas()
        if not enviadas:
            self.stdout.write('Sin alertas que enviar.')
            return
        for a in enviadas:
            self.stdout.write(self.style.WARNING(f"Alerta enviada: {a['anuncio']} · CPA {a['cpa_real']}"))
        self.stdout.write(self.style.SUCCESS(f'{len(enviadas)} alerta(s) enviada(s) a n8n.'))
