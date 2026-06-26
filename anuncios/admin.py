# anuncios/admin.py
from django.contrib import admin

from .models import (CuentaPublicitaria, CampanaMeta, InsightDiarioMeta,
                     InsightHorarioMeta, MatchProductoAnuncio, UmbralAlerta, AlertaEnviada)


@admin.register(CuentaPublicitaria)
class CuentaPublicitariaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'plataforma', 'ad_account_id', 'integracion', 'activo')
    list_filter = ('plataforma', 'activo')


@admin.register(CampanaMeta)
class CampanaMetaAdmin(admin.ModelAdmin):
    list_display = ('ad_name', 'adset_name', 'campaign_name', 'cuenta', 'incluir_en_extraccion')
    list_filter = ('incluir_en_extraccion', 'cuenta')
    list_editable = ('incluir_en_extraccion',)
    search_fields = ('ad_name', 'adset_name', 'campaign_name', 'ad_id')


@admin.register(InsightDiarioMeta)
class InsightDiarioMetaAdmin(admin.ModelAdmin):
    list_display = ('campana', 'fecha', 'gasto', 'impresiones', 'clicks', 'resultados')
    list_filter = ('fecha',)


@admin.register(MatchProductoAnuncio)
class MatchProductoAnuncioAdmin(admin.ModelAdmin):
    list_display = ('campana', 'producto', 'origen', 'confianza', 'creado_por')
    list_filter = ('origen',)


admin.site.register(InsightHorarioMeta)
admin.site.register(UmbralAlerta)
admin.site.register(AlertaEnviada)
