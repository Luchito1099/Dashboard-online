# core/management/commands/esquema_bd.py
"""Genera la documentación del esquema de la base de datos a partir de los modelos
de Django. Produce un Markdown con: índice de tablas, diagrama ER (Mermaid), bloque
DBML (para dbdiagram.io) y el detalle de cada tabla con sus campos y relaciones.

Uso:
    python manage.py esquema_bd                 # escribe docs/ESQUEMA_BD.md
    python manage.py esquema_bd --salida x.md   # ruta personalizada
    python manage.py esquema_bd --stdout        # imprime en consola

Vuelve a ejecutarlo cada vez que agregues o cambies modelos para mantenerlo al día.
"""
from datetime import datetime
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand

# Apps del proyecto (más auth.User, que se referencia desde varios modelos)
APPS_PROYECTO = ['core', 'capacitacion', 'productos', 'herramientas', 'integraciones', 'rotulador']

# Mapa de tipos internos de Django → tipo corto para los diagramas
TIPOS = {
    'AutoField': 'int', 'BigAutoField': 'bigint', 'SmallAutoField': 'int',
    'IntegerField': 'int', 'BigIntegerField': 'bigint',
    'PositiveIntegerField': 'int', 'PositiveSmallIntegerField': 'int', 'SmallIntegerField': 'int',
    'CharField': 'varchar', 'TextField': 'text', 'SlugField': 'varchar', 'EmailField': 'varchar',
    'URLField': 'varchar', 'EncryptedTextField': 'text',
    'BooleanField': 'bool', 'DecimalField': 'decimal', 'FloatField': 'float',
    'DateTimeField': 'datetime', 'DateField': 'date', 'TimeField': 'time',
    'JSONField': 'json', 'UUIDField': 'uuid',
    'ForeignKey': 'int', 'OneToOneField': 'int', 'ManyToManyField': 'm2m',
}


class Command(BaseCommand):
    help = 'Genera/actualiza la documentación del esquema de la base de datos (docs/ESQUEMA_BD.md).'

    def add_arguments(self, parser):
        parser.add_argument('--salida', default=str(Path(settings.BASE_DIR) / 'docs' / 'ESQUEMA_BD.md'))
        parser.add_argument('--stdout', action='store_true', help='Imprime en consola en vez de escribir el archivo.')

    def handle(self, *args, **opts):
        modelos = self._recolectar_modelos()
        nombres = {m.__name__ for m in modelos}
        texto = self._render(modelos, nombres)

        if opts['stdout']:
            self.stdout.write(texto)
            return
        ruta = Path(opts['salida'])
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(texto, encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(f'Esquema escrito en {ruta} ({len(modelos)} tablas).'))

    # ── Recolección ──
    def _recolectar_modelos(self):
        modelos = []
        for cfg in apps.get_app_configs():
            if cfg.label in APPS_PROYECTO:
                modelos.extend(sorted(cfg.get_models(), key=lambda m: m.__name__))
        # auth.User al final (se referencia desde muchos modelos)
        User = apps.get_model('auth', 'User')
        modelos.append(User)
        return modelos

    def _campos(self, model):
        """Lista de dicts con la info de cada columna local del modelo."""
        filas = []
        for f in model._meta.local_fields:
            rel = None
            if f.is_relation and f.related_model is not None:
                rel = {
                    'modelo': f.related_model.__name__,
                    'tabla': f.related_model._meta.db_table,
                    'tipo': 'O2O' if f.one_to_one else 'FK',
                    'on_delete': getattr(getattr(f, 'remote_field', None), 'on_delete', None).__name__
                    if getattr(getattr(f, 'remote_field', None), 'on_delete', None) else '',
                }
            filas.append({
                'nombre': f.attname,            # ej. integracion_id
                'campo': f.name,
                'tipo': f.get_internal_type(),
                'tipo_corto': TIPOS.get(f.get_internal_type(), f.get_internal_type().lower()),
                'pk': f.primary_key,
                'null': f.null,
                'unique': f.unique,
                'max_length': getattr(f, 'max_length', None),
                'choices': bool(getattr(f, 'choices', None)),
                'rel': rel,
            })
        # M2M
        m2m = []
        for f in model._meta.local_many_to_many:
            m2m.append({
                'campo': f.name,
                'modelo': f.related_model.__name__,
                'through': f.remote_field.through.__name__ if f.remote_field.through else None,
            })
        return filas, m2m

    # ── Render ──
    def _render(self, modelos, nombres):
        L = []
        L.append('# Esquema de la base de datos · Dashboard')
        L.append('')
        L.append(f'> Generado automáticamente por `python manage.py esquema_bd` el '
                 f'{datetime.now():%Y-%m-%d %H:%M}. **No editar a mano** (se sobrescribe). '
                 f'Para análisis y mejoras ver `docs/ESQUEMA_NOTAS.md`.')
        L.append('')
        L.append('## Cómo visualizarlo')
        L.append('- **Diagrama ER (rápido):** copia el bloque *Mermaid* en https://mermaid.live')
        L.append('- **Herramienta de tablas:** copia el bloque *DBML* en https://dbdiagram.io (Import → DBML)')
        L.append('')

        # Índice por app
        L.append('## Tablas por módulo')
        por_app = {}
        for m in modelos:
            por_app.setdefault(m._meta.app_label, []).append(m)
        for app in list(APPS_PROYECTO) + ['auth']:
            if app not in por_app:
                continue
            tablas = ', '.join(f'`{m._meta.db_table}`' for m in por_app[app])
            L.append(f'- **{app}**: {tablas}')
        L.append('')

        # Diagrama Mermaid
        L.append('## Diagrama ER (Mermaid)')
        L.append('```mermaid')
        L.append('erDiagram')
        for m in modelos:
            filas, _ = self._campos(m)
            L.append(f'    {m.__name__} {{')
            for f in filas:
                keys = []
                if f['pk']:
                    keys.append('PK')
                if f['rel']:
                    keys.append('FK')
                key = ','.join(keys)
                L.append(f"        {f['tipo_corto']} {f['nombre']}{(' ' + key) if key else ''}")
            L.append('    }')
        # relaciones
        for m in modelos:
            filas, m2m = self._campos(m)
            for f in filas:
                if f['rel'] and f['rel']['modelo'] in nombres:
                    simb = '||--||' if f['rel']['tipo'] == 'O2O' else '}o--||'
                    L.append(f"    {m.__name__} {simb} {f['rel']['modelo']} : {f['campo']}")
            for r in m2m:
                if r['modelo'] in nombres:
                    L.append(f"    {m.__name__} }}o--o{{ {r['modelo']} : {r['campo']}")
        L.append('```')
        L.append('')

        # DBML
        L.append('## DBML (dbdiagram.io)')
        L.append('```dbml')
        for m in modelos:
            filas, _ = self._campos(m)
            L.append(f'Table {m._meta.db_table} {{')
            for f in filas:
                attrs = []
                if f['pk']:
                    attrs.append('pk')
                if f['unique'] and not f['pk']:
                    attrs.append('unique')
                if f['null']:
                    attrs.append('null')
                if f['rel'] and f['rel']['modelo'] in nombres:
                    flecha = '-' if f['rel']['tipo'] == 'O2O' else '>'
                    attrs.append(f"ref: {flecha} {f['rel']['tabla']}.id")
                suf = f" [{', '.join(attrs)}]" if attrs else ''
                L.append(f"  {f['nombre']} {f['tipo_corto']}{suf}")
            L.append('}')
            L.append('')
        L.append('```')
        L.append('')

        # Detalle por tabla
        L.append('## Detalle de cada tabla')
        for m in modelos:
            filas, m2m = self._campos(m)
            doc = (m.__doc__ or '').strip().split('\n')[0] if m.__doc__ else ''
            L.append(f'### `{m._meta.db_table}` — {m.__name__}')
            if doc:
                L.append(f'_{doc}_')
            L.append('')
            L.append('| Columna | Tipo | Nulo | Llave / Relación | Notas |')
            L.append('|---|---|---|---|---|')
            for f in filas:
                rel = ''
                if f['pk']:
                    rel = 'PK'
                elif f['rel']:
                    rel = f"{f['rel']['tipo']} → `{f['rel']['tabla']}`" + (f" ({f['rel']['on_delete']})" if f['rel']['on_delete'] else '')
                notas = []
                if f['unique'] and not f['pk']:
                    notas.append('único')
                if f['max_length']:
                    notas.append(f"máx {f['max_length']}")
                if f['choices']:
                    notas.append('choices')
                L.append(f"| {f['nombre']} | {f['tipo']} | {'sí' if f['null'] else 'no'} | {rel} | {', '.join(notas)} |")
            for r in m2m:
                th = f" (through `{r['through']}`)" if r['through'] else ''
                L.append(f"| {r['campo']} | M2M | — | M2M → `{r['modelo']}`{th} | |")
            # unique_together
            ut = m._meta.unique_together
            if ut:
                combos = '; '.join('(' + ', '.join(c) + ')' for c in ut)
                L.append('')
                L.append(f'**Únicos compuestos:** {combos}')
            L.append('')

        return '\n'.join(L)
