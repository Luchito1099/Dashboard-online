# anuncios/urls.py
from django.urls import path

from . import views

app_name = 'anuncios'

urlpatterns = [
    # Dashboards (sub-pestañas: ?vista=diario|productos|heatmap)
    path('publicidad/', views.dashboard, name='dashboard'),
    # Matching producto ↔ anuncio
    path('publicidad/matching/', views.matching_pendiente, name='matching'),
    path('publicidad/matching/confirmar/', views.confirmar_match, name='confirmar_match'),
    path('publicidad/matching/confirmar-campana/', views.confirmar_match_campana, name='confirmar_match_campana'),
    path('publicidad/matching/<int:campana_id>/quitar/', views.quitar_match, name='quitar_match'),
    # Ajustes (solo admin)
    path('publicidad/ajustes/', views.ajustes, name='ajustes'),
    path('publicidad/cuenta/<int:cuenta_id>/probar/', views.probar_cuenta, name='probar_cuenta'),
    path('publicidad/cuenta/<int:cuenta_id>/sincronizar/', views.sincronizar_cuenta, name='sincronizar_cuenta'),
    # API para el gráfico del Inicio (Gasto Meta vs Pedidos)
    path('publicidad/api/inicio-serie/', views.api_inicio_serie, name='api_inicio_serie'),
    # API para el mapa de calor del Inicio (pedidos/gasto por día×hora)
    path('publicidad/api/inicio-heatmap/', views.api_inicio_heatmap, name='api_inicio_heatmap'),
    # Webhook de n8n (alternativa; la extracción principal es directa a la Graph API)
    path('publicidad/webhook/n8n/', views.webhook_n8n_meta, name='webhook_n8n'),
]
