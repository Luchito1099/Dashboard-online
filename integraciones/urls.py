# integraciones/urls.py
from django.urls import path
from . import views

app_name = 'integraciones'

urlpatterns = [
    path('integraciones/', views.lista, name='lista'),
    path('integraciones/crear/', views.crear, name='crear'),
    path('integraciones/editar/<int:integracion_id>/', views.editar, name='editar'),
    path('integraciones/eliminar/<int:integracion_id>/', views.eliminar, name='eliminar'),
    path('integraciones/probar/<int:integracion_id>/', views.probar, name='probar'),
    path('integraciones/sincronizar/<int:integracion_id>/', views.sincronizar, name='sincronizar'),
    path('integraciones/pedidos/<int:integracion_id>/', views.pedidos, name='pedidos'),
    # OAuth de Shopify
    path('integraciones/oauth/iniciar/<int:integracion_id>/', views.oauth_iniciar, name='oauth_iniciar'),
    path('integraciones/oauth/callback/', views.oauth_callback, name='oauth_callback'),
    # Webhooks (tiempo real)
    path('integraciones/webhook/activar/<int:integracion_id>/', views.activar_webhook, name='activar_webhook'),
    path('integraciones/webhook/shopify/<int:integracion_id>/', views.webhook_shopify, name='webhook'),
    # Shalom (rastreo por scraper)
    path('integraciones/shalom/<int:integracion_id>/envios/', views.shalom_envios, name='shalom_envios'),
    path('integraciones/shalom/<int:integracion_id>/actualizar/', views.api_shalom_actualizar, name='shalom_actualizar'),
    path('integraciones/shalom/<int:integracion_id>/estado/', views.api_shalom_estado, name='shalom_estado'),
    path('integraciones/shalom/<int:integracion_id>/api/envios/', views.api_shalom_envios, name='shalom_api_envios'),
    path('integraciones/shalom/envio/<int:envio_id>/validar/', views.api_shalom_validar, name='shalom_validar'),
    path('integraciones/shalom/envio/<int:envio_id>/notificar/', views.api_shalom_notificar, name='shalom_notificar'),
]
