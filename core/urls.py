# core/urls.py
from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    # Configuración de usuarios y del sistema (solo admin)
    path('configuracion/', views.configuracion, name='configuracion'),
    # Página de respaldo cuando el vendedor no tiene módulos habilitados
    path('sin-acceso/', views.sin_acceso, name='sin_acceso'),
    # Buscador global del topbar (devuelve JSON)
    path('buscar/', views.api_buscar, name='buscar'),
]
