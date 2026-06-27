# Limpia filas de StockProducto duplicadas (mismo producto, variante y almacén) que
# se crearon por una condición de carrera. Conserva una sola fila por grupo (la de mayor
# cantidad = el valor que el usuario ve) y elimina el resto. Debe correr ANTES de aplicar
# las restricciones únicas parciales.
from collections import defaultdict

from django.db import migrations


def dedupe(apps, schema_editor):
    StockProducto = apps.get_model('inventario', 'StockProducto')
    grupos = defaultdict(list)
    for sp in StockProducto.objects.all():
        grupos[(sp.producto_id, sp.variante_id, sp.almacen_id)].append(sp)
    for filas in grupos.values():
        if len(filas) > 1:
            filas.sort(key=lambda r: r.cantidad, reverse=True)   # conserva la de mayor cantidad
            for r in filas[1:]:
                r.delete()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0002_alter_stockproducto_unique_together_and_more'),
    ]

    operations = [
        migrations.RunPython(dedupe, noop),
    ]
