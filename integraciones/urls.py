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
]
