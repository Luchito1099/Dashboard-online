# productos/urls.py
from django.urls import path
from . import views

app_name = 'productos'

urlpatterns = [
    # Catálogo de productos (grid + buscador + panel de detalle)
    path('productos/', views.catalogo, name='catalogo'),
    # Catálogo con un producto abierto en el panel de detalle (ficha completa)
    path('productos/<int:producto_id>/', views.detalle, name='detalle'),
    # Ficha rápida compacta para llamadas en vivo
    path('productos/ficha/<int:producto_id>/', views.ficha_rapida, name='ficha_rapida'),
    # Reconocer productos de pedidos (vincular nombres externos al catálogo) — solo admin
    path('productos/reconocer/', views.reconocer_productos, name='reconocer'),
    path('productos/reconocer/vincular/', views.vincular_producto, name='vincular'),
    # Administración de productos (solo admin)
    path('productos/admin/', views.admin_productos, name='admin'),
    path('productos/crear/', views.crear_producto, name='crear'),
    path('productos/editar/<int:producto_id>/', views.editar_producto, name='editar'),
    path('productos/eliminar/<int:producto_id>/', views.eliminar_producto, name='eliminar'),
]
