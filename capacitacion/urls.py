# capacitacion/urls.py
from django.urls import path
from . import views

app_name = 'capacitacion'

urlpatterns = [
    # Runbook diario (vista principal de la vendedora)
    path('capacitacion/', views.index, name='index'),
    # Marca/desmarca una tarea como completada (AJAX, devuelve JSON)
    path('capacitacion/toggle/<int:tarea_id>/', views.toggle_tarea, name='toggle_tarea'),
    # Guarda los cambios de una tarea (solo admin/superuser, POST)
    path('capacitacion/editar/<int:tarea_id>/', views.editar_tarea, name='editar_tarea'),
    # Panel de administración del runbook (solo admin/superuser)
    path('capacitacion/admin/', views.admin_panel, name='admin_panel'),
    # Crea una tarea nueva (solo admin/superuser, POST)
    path('capacitacion/tarea/crear/', views.crear_tarea, name='crear_tarea'),
    # Gestión de bloques de tareas (solo admin/superuser, POST)
    path('capacitacion/bloque/crear/', views.crear_bloque, name='crear_bloque'),
    path('capacitacion/bloque/editar/<int:bloque_id>/', views.editar_bloque, name='editar_bloque'),
]
