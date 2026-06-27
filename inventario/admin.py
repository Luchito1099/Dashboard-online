# inventario/admin.py
from django.contrib import admin

from .models import Almacen, StockProducto, MovimientoStock, ConfigReposicion


@admin.register(Almacen)
class AlmacenAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'integracion', 'es_principal', 'activo', 'orden')
    list_editable = ('es_principal', 'activo', 'orden')


@admin.register(StockProducto)
class StockProductoAdmin(admin.ModelAdmin):
    list_display = ('producto', 'almacen', 'cantidad', 'actualizado')
    list_filter = ('almacen',)
    search_fields = ('producto__nombre',)


@admin.register(MovimientoStock)
class MovimientoStockAdmin(admin.ModelAdmin):
    list_display = ('creado', 'producto', 'almacen', 'delta', 'motivo', 'pedido', 'usuario')
    list_filter = ('motivo', 'almacen')
    search_fields = ('producto__nombre',)


@admin.register(ConfigReposicion)
class ConfigReposicionAdmin(admin.ModelAdmin):
    list_display = ('producto', 'dias_entrega', 'dias_seguridad', 'dias_cobertura', 'activo')
    list_editable = ('dias_entrega', 'dias_seguridad', 'dias_cobertura', 'activo')
