from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path('', include('capacitacion.urls')),
    path('', include('productos.urls')),
    path('', include('herramientas.urls')),
    path('', include('integraciones.urls')),
    path('', include('rotulador.urls')),
    path('', include('anuncios.urls')),
    path('', include('inventario.urls')),
    path('accounts/', include('django.contrib.auth.urls')),
]