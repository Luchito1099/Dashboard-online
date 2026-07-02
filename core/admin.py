from django.contrib import admin

from .models import ReporteMatching


@admin.register(ReporteMatching)
class ReporteMatchingAdmin(admin.ModelAdmin):
    list_display = ('creado', 'total_items_sin_match', 'total_monto_afectado', 'generado_por')
    readonly_fields = ('creado', 'total_items_sin_match', 'total_monto_afectado', 'detalle', 'generado_por')
    ordering = ('-creado',)
