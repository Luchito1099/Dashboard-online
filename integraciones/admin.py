# integraciones/admin.py
from django.contrib import admin
from .models import Integracion


@admin.register(Integracion)
class IntegracionAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'categoria', 'proveedor', 'activo', 'ultimo_test_ok', 'creado')
    list_filter = ('categoria', 'proveedor', 'activo')
    search_fields = ('nombre', 'etiqueta', 'tienda_url')
