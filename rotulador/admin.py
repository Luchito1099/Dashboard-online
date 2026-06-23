# rotulador/admin.py
from django.contrib import admin
from .models import Rotulo, RotuladorConfig


@admin.register(Rotulo)
class RotuloAdmin(admin.ModelAdmin):
    list_display = ('nombres', 'celular', 'agencia', 'producto', 'origen', 'creado')
    list_filter = ('origen',)
    search_fields = ('nombres', 'celular', 'dni', 'destino', 'producto')


admin.site.register(RotuladorConfig)
