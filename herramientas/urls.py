# herramientas/urls.py
from django.urls import path
from . import views

app_name = 'herramientas'

urlpatterns = [
    path('herramientas/', views.lista, name='lista'),
    path('herramientas/admin/', views.admin_herramientas, name='admin'),
    path('herramientas/crear/', views.crear_herramienta, name='crear'),
    path('herramientas/editar/<int:herramienta_id>/', views.editar_herramienta, name='editar'),
    path('herramientas/eliminar/<int:herramienta_id>/', views.eliminar_herramienta, name='eliminar'),
]
