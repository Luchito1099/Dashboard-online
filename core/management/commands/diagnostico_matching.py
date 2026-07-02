# core/management/commands/diagnostico_matching.py
"""Genera el reporte de salud de datos del matching de productos.

Uso:
    python manage.py diagnostico_matching --texto        # legible (consola / cron)
    python manage.py diagnostico_matching --json         # JSON (para vistas/integraciones)
    python manage.py diagnostico_matching --guardar       # además persiste un ReporteMatching
    python manage.py diagnostico_matching --dias 60       # ventana de días para huecos de sync
"""
import json

from django.core.management.base import BaseCommand

from core.diagnostico import generar_diagnostico, guardar_snapshot


class Command(BaseCommand):
    help = 'Reporte de salud de datos del matching (items sin resolver, alias, huecos de sync, anuncios sin match).'

    def add_arguments(self, parser):
        parser.add_argument('--json', action='store_true', help='Salida en JSON.')
        parser.add_argument('--texto', action='store_true', help='Salida legible (por defecto).')
        parser.add_argument('--guardar', action='store_true',
                            help='Persiste un ReporteMatching (snapshot) además de imprimir.')
        parser.add_argument('--dias', type=int, default=30,
                            help='Ventana de días para detectar huecos de sincronización (def. 30).')

    def handle(self, *args, **opts):
        data = generar_diagnostico(dias=opts['dias'])

        if opts['guardar']:
            snap = guardar_snapshot(data)
            data['snapshot_id'] = snap.id

        # --json tiene prioridad; si no se pide nada, va --texto.
        if opts['json']:
            self.stdout.write(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            self._texto(data)

    def _texto(self, data):
        # Salida ASCII-safe: la consola de Windows (cp1252) no soporta caracteres
        # como box-drawing/flechas y rompería un cron.
        w = self.stdout.write
        s = self.style
        w(s.MIGRATE_HEADING('\n=== Salud de datos - matching ==='))
        w(f'Generado: {data["generado"]}')
        if 'snapshot_id' in data:
            w(s.SUCCESS(f'Snapshot guardado: ReporteMatching #{data["snapshot_id"]}'))

        # (a) items sin match
        a = data['items_sin_match']
        w(s.MIGRATE_HEADING(f'\n(a) PedidoItem sin producto: {a["total_items"]} '
                            f'- monto afectado S/ {a["total_monto"]:.2f}'))
        for g in a['grupos'][:30]:
            var = f' [{g["variante"]}]' if g['variante'] else ''
            w(f'   {g["ocurrencias"]:>4}x  {g["nombre"]}{var}  '
              f'(cant {g["cantidad"]}, S/ {g["monto"]:.2f})')
        if len(a['grupos']) > 30:
            w(f'   ... y {len(a["grupos"]) - 30} grupo(s) mas')

        # (b) alias problematicos
        ap = data['alias_problemas']
        w(s.MIGRATE_HEADING(f'\n(b) Alias duplicados: {len(ap["duplicados"])} '
                            f'- huerfanos: {len(ap["huerfanos"])}'))
        for d in ap['duplicados']:
            marca = s.ERROR('  [CONFLICTO]') if d['conflicto'] else ''
            w(f'   "{d["nombre_externo"]}" x{len(d["entradas"])}{marca}')
            for e in d['entradas']:
                w(f'       {e["integracion"]} -> {e["producto"]} (sku {e["sku_externo"] or "-"})')
        for h in ap['huerfanos'][:20]:
            w(f'   huerfano: "{h["nombre_externo"]}" -> {h["producto"]}')

        # (c) huecos de sincronizacion
        w(s.MIGRATE_HEADING('\n(c) Pedidos por integracion / huecos de sync'))
        for p in data['pedidos_por_fecha']:
            w(f'   {p["integracion"]}: {p["total"]} pedido(s) en la ventana')
            if p['huecos']:
                w(s.WARNING(f'       {len(p["huecos"])} dia(s) sin pedidos: '
                            f'{", ".join(p["huecos"][:10])}'
                            f'{" ..." if len(p["huecos"]) > 10 else ""}'))

        # (d) campanas sin match
        cs = data['campanas_sin_match']
        w(s.MIGRATE_HEADING(f'\n(d) Campanas Meta activas sin match a producto: {len(cs)}'))
        for c in cs[:30]:
            w(f'   {c["cuenta"]} - {c["campaign_name"]} - {c["ad_name"]}')
        if len(cs) > 30:
            w(f'   ... y {len(cs) - 30} mas')

        # resumen por integracion
        w(s.MIGRATE_HEADING('\n% de matcheo por integracion'))
        for r in data['resumen_por_integracion']:
            w(f'   {r["integracion"]}: {r["pct_match"]}% '
              f'({r["matcheados"]}/{r["total"]} items, {r["sin_match"]} sin match)')
        w('')
