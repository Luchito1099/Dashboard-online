from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path('', include('capacitacion.urls')),
    path('', include('productos.urls')),
    path('', include('herramientas.urls')),
    path('accounts/', include('django.contrib.auth.urls')),
]