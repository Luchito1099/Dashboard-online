# rotulador/urls.py
from django.urls import path
from . import views

app_name = 'rotulador'

urlpatterns = [
    path('rotulador/', views.index, name='index'),
    path('rotulador/api/rotulos/', views.api_rotulos, name='api_rotulos'),
    path('rotulador/api/rotulos/<int:rotulo_id>/', views.api_rotulo_detail, name='api_rotulo_detail'),
    path('rotulador/api/pedidos/', views.api_pedidos, name='api_pedidos'),
    path('rotulador/api/config/', views.api_config, name='api_config'),
    path('rotulador/api/extraer/', views.api_extraer, name='api_extraer'),
]
