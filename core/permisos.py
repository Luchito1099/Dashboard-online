# core/permisos.py
"""Helpers para los permisos del rol vendedor configurables desde Configuración.
El admin siempre tiene acceso total; el vendedor depende de ConfiguracionSistema."""
from django.urls import reverse

from .models import ConfiguracionSistema


def _es_admin(user):
    # Import local para evitar import circular (capacitacion.views ↔ core).
    from capacitacion.views import es_admin
    return es_admin(user)


def puede_ver(user, flag):
    """True si el usuario puede ver el módulo. Admin siempre; vendedor según el flag
    (atributo de ConfiguracionSistema, ej. 'vendedor_puede_ver_inicio')."""
    if _es_admin(user):
        return True
    return getattr(ConfiguracionSistema.get_solo(), flag, False)


def destino_vendedor(user):
    """URL del primer módulo que el vendedor SÍ puede ver. Se usa como destino seguro
    al bloquear el acceso, evitando bucles de redirección. Si no puede ver nada,
    devuelve la página 'sin acceso'."""
    if _es_admin(user):
        return reverse('core:home')

    cfg = ConfiguracionSistema.get_solo()
    if cfg.vendedor_puede_ver_inicio:
        return reverse('core:home')
    if cfg.vendedor_puede_ver_capacitacion:
        return reverse('capacitacion:index')
    if cfg.vendedor_puede_ver_productos:
        return reverse('productos:catalogo')
    if cfg.vendedor_puede_ver_herramientas:
        return reverse('herramientas:lista')
    return reverse('core:sin_acceso')
