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
]
