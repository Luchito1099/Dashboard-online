# integraciones/management/commands/shalom_scheduler.py
"""Planificador en Python para las integraciones Shalom.
Corre como proceso aparte (NO dentro de Gunicorn). Cada ~60s revisa las
integraciones Shalom activas y dispara una corrida si toca según su horario.

Reglas de disparo:
  - `horarios` (lista "HH:MM"): dispara si la hora actual coincide (±2 min) y no
    corrió ya en ese horario hoy.
  - si no hay `horarios`, usa `intervalo_horas` desde la última corrida.

Uso:  python manage.py shalom_scheduler
"""
import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from integraciones.models import Integracion, ConfigShalom
from integraciones import shalom_runner


def _toca_por_intervalo(cfg, ahora):
    if not cfg.ultima_corrida:
        return True
    return ahora - cfg.ultima_corrida >= timedelta(hours=cfg.intervalo_horas or 6)


def _toca_por_horario(cfg, ahora):
    actual = ahora.strftime('%H:%M')
    for h in (cfg.horarios or []):
        try:
            hh, mm = h.split(':')
            objetivo = ahora.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
        except (ValueError, AttributeError):
            continue
        if abs((ahora - objetivo).total_seconds()) <= 120:
            # No repetir si ya corrió en los últimos 10 min
            if not cfg.ultima_corrida or (ahora - cfg.ultima_corrida).total_seconds() > 600:
                return True
    return False


class Command(BaseCommand):
    help = 'Planificador de corridas Shalom (proceso de larga duración).'

    def handle(self, *args, **opts):
        self.stdout.write('Scheduler Shalom iniciado. Ctrl+C para detener.')
        while True:
            ahora = timezone.localtime()
            integraciones = Integracion.objects.filter(proveedor='shalom', activo=True)
            for integ in integraciones:
                cfg, _ = ConfigShalom.objects.get_or_create(integracion=integ)
                if cfg.corriendo:
                    continue
                toca = _toca_por_horario(cfg, ahora) if cfg.horarios else _toca_por_intervalo(cfg, ahora)
                if toca:
                    self.stdout.write(f'[{ahora:%H:%M}] Disparando «{integ.nombre}»…')
                    try:
                        ok, msg = shalom_runner.correr(integ, tipo='auto')
                        self.stdout.write(('  OK: ' if ok else '  ERROR: ') + msg)
                    except Exception as e:
                        self.stdout.write(f'  ERROR: {e}')
            time.sleep(60)
