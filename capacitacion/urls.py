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
    # Elimina una tarea (solo admin/superuser, POST)
    path('capacitacion/tarea/eliminar/<int:tarea_id>/', views.eliminar_tarea, name='eliminar_tarea'),
    # Gestión de bloques de tareas (solo admin/superuser, POST)
    path('capacitacion/bloque/crear/', views.crear_bloque, name='crear_bloque'),
    path('capacitacion/bloque/editar/<int:bloque_id>/', views.editar_bloque, name='editar_bloque'),
    # Estrategias de venta (catálogo + CRUD admin)
    path('estrategias/', views.estrategias, name='estrategias'),
    path('estrategias/admin/', views.estrategias_admin, name='estrategias_admin'),
    path('estrategias/crear/', views.crear_estrategia, name='crear_estrategia'),
    path('estrategias/editar/<int:estrategia_id>/', views.editar_estrategia, name='editar_estrategia'),
    path('estrategias/eliminar/<int:estrategia_id>/', views.eliminar_estrategia, name='eliminar_estrategia'),
    # Lecciones (mini-clases en video)
    path('lecciones/', views.lecciones, name='lecciones'),
    path('lecciones/<int:leccion_id>/', views.leccion_detalle, name='leccion_detalle'),
    path('lecciones/<int:leccion_id>/completar/', views.leccion_completar, name='leccion_completar'),
    path('lecciones/admin/', views.lecciones_admin, name='lecciones_admin'),
    path('lecciones/crear/', views.crear_leccion, name='crear_leccion'),
    path('lecciones/editar/<int:leccion_id>/', views.editar_leccion, name='editar_leccion'),
    path('lecciones/eliminar/<int:leccion_id>/', views.eliminar_leccion, name='eliminar_leccion'),
]
