from django.contrib import admin

from .models import Estrategia


@admin.register(Estrategia)
class EstrategiaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'activo', 'orden')
    list_editable = ('activo', 'orden')
    search_fields = ('nombre', 'descripcion')
