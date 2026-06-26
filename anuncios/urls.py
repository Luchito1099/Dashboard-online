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
    path('publicidad/matching/<int:campana_id>/quitar/', views.quitar_match, name='quitar_match'),
    # Ajustes (solo admin)
    path('publicidad/ajustes/', views.ajustes, name='ajustes'),
    # Webhook de n8n (sin login; autenticado por firma)
    path('publicidad/webhook/n8n/', views.webhook_n8n_meta, name='webhook_n8n'),
]
