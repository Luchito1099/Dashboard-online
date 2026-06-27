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
    # Módulo Pedidos (vista unificada de todas las fuentes)
    path('pedidos/', views.pedidos_modulo, name='pedidos_modulo'),
    path('pedidos/<int:pedido_id>/editar/', views.pedido_editar, name='pedido_editar'),
    path('pedidos/<int:pedido_id>/seguimiento/', views.pedido_seguimiento_editar, name='pedido_seguimiento_editar'),
    path('pedidos/<int:pedido_id>/historial/', views.pedido_historial, name='pedido_historial'),
    path('pedidos/historial/<int:log_id>/revertir/', views.pedido_revertir, name='pedido_revertir'),
    path('pedidos/nuevos/', views.pedidos_nuevos, name='pedidos_nuevos'),
    path('pedidos/recientes/', views.pedidos_recientes, name='pedidos_recientes'),
    path('pedidos/filtro/', views.pedido_filtro, name='pedido_filtro'),
    # Registro de pedidos (alta manual)
    path('registro-pedidos/', views.registro_pedidos, name='registro_pedidos'),
    path('registro-pedidos/crear/', views.registro_crear, name='registro_crear'),
    path('registro-pedidos/ia-autocompletar/', views.registro_ia_autocompletar, name='registro_ia_autocompletar'),
    # Cruce de pedidos por Excel (confirmación masiva)
    path('pedidos/cruce-excel/', views.cruce_excel, name='cruce_excel'),
    path('pedidos/cruce-excel/previa/', views.cruce_excel_preview, name='cruce_excel_preview'),
    path('pedidos/cruce-excel/ia/', views.cruce_excel_ia, name='cruce_excel_ia'),
    path('pedidos/cruce-excel/aplicar/', views.cruce_excel_aplicar, name='cruce_excel_aplicar'),
    path('pedidos/cruce-excel/pendientes/guardar/', views.cruce_guardar_pendientes, name='cruce_guardar_pendientes'),
    path('pedidos/pendientes/', views.pendientes, name='pendientes'),
    path('pedidos/pendientes/borrar/', views.pendientes_borrar, name='pendientes_borrar'),
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
    path('integraciones/shalom/<int:integracion_id>/detener/', views.api_shalom_detener, name='shalom_detener'),
    path('integraciones/shalom/<int:integracion_id>/importar/', views.api_shalom_importar, name='shalom_importar'),
    path('integraciones/shalom/<int:integracion_id>/api/envios/', views.api_shalom_envios, name='shalom_api_envios'),
    path('integraciones/shalom/envio/<int:envio_id>/validar/', views.api_shalom_validar, name='shalom_validar'),
    path('integraciones/shalom/envio/<int:envio_id>/notificar/', views.api_shalom_notificar, name='shalom_notificar'),
]
