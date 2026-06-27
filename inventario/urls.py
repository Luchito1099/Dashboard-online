# inventario/urls.py
from django.urls import path

from . import views

app_name = 'inventario'

urlpatterns = [
    path('inventario/', views.inventario, name='inventario'),
    path('inventario/ajustar/', views.ajustar_stock, name='ajustar_stock'),
    path('inventario/reposicion/', views.reposicion, name='reposicion'),
    path('inventario/reposicion/config/', views.guardar_config, name='guardar_config'),
    path('inventario/almacenes/', views.almacenes, name='almacenes'),
]
