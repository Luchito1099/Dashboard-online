# core/permisos.py
"""Helpers para los permisos del rol vendedor configurables desde Configuración.
El admin siempre tiene acceso total; el vendedor depende de ConfiguracionSistema."""
from django.urls import reverse

from .models import ConfiguracionSistema


def _es_admin(user):
    # Import local para evitar import circular (capacitacion.views ↔ core).
    from capacitacion.views import es_admin
    return es_admin(user)


def _es_analista(user):
    """True si el usuario tiene rol 'analista' (no superuser, ese es admin)."""
    return hasattr(user, 'perfil') and user.perfil.rol == 'analista'


def _es_marketing(user):
    """True si el usuario tiene rol 'marketing' (Analista de Marketing)."""
    return hasattr(user, 'perfil') and user.perfil.rol == 'marketing'


# ── Permisos del módulo Publicidad (Meta Ads) ──

def puede_ver_ads(user):
    """Acceso a los dashboards de Publicidad. Admin y marketing."""
    return _es_admin(user) or _es_marketing(user)


def puede_matching(user):
    """Puede hacer matching producto↔anuncio. Admin y marketing."""
    return _es_admin(user) or _es_marketing(user)


def puede_admin_ads(user):
    """Administración de Publicidad (cuentas, marcar qué se extrae, umbrales de alerta).
    Solo admin (el marketing NO controla qué campañas entran ni ve costos)."""
    return _es_admin(user)


def puede_ver(user, flag):
    """True si el usuario puede ver el módulo. Admin siempre; vendedor según el flag
    (atributo de ConfiguracionSistema, ej. 'vendedor_puede_ver_inicio')."""
    if _es_admin(user):
        return True
    return getattr(ConfiguracionSistema.get_solo(), flag, False)


def puede_ver_pedidos(user):
    """Acceso al módulo Pedidos (cualquiera de sus pestañas). Admin y analista siempre;
    vendedor si tiene algún permiso de Pedidos (listado, seguimiento o avances)."""
    if _es_admin(user) or _es_analista(user):
        return True
    cfg = ConfiguracionSistema.get_solo()
    return any([cfg.vendedor_puede_ver_pedidos, cfg.vendedor_puede_editar_pedidos,
                cfg.vendedor_puede_ver_seguimiento, cfg.vendedor_puede_editar_seguimiento,
                cfg.vendedor_puede_ver_avances])


def puede_ver_listado(user):
    """Acceso a la pestaña Listado (datos financieros). Admin y analista siempre;
    vendedor según los flags clásicos de ver/editar pedidos."""
    if _es_admin(user) or _es_analista(user):
        return True
    cfg = ConfiguracionSistema.get_solo()
    return cfg.vendedor_puede_ver_pedidos or cfg.vendedor_puede_editar_pedidos


def puede_ver_seguimiento(user):
    """Acceso a la vista Seguimiento. Admin y analista siempre; vendedor según el flag."""
    if _es_admin(user) or _es_analista(user):
        return True
    cfg = ConfiguracionSistema.get_solo()
    return cfg.vendedor_puede_ver_seguimiento or cfg.vendedor_puede_editar_seguimiento


def puede_editar_seguimiento(user):
    """Permiso de edición de Seguimiento. Admin siempre; analista según su flag;
    vendedor según el flag de editar seguimiento."""
    if _es_admin(user):
        return True
    cfg = ConfiguracionSistema.get_solo()
    if _es_analista(user):
        return cfg.analista_puede_editar_seguimiento
    return cfg.vendedor_puede_editar_seguimiento


def puede_ver_avances(user):
    """Acceso a la vista Avances. Admin y analista siempre (completo); vendedor según el flag."""
    if _es_admin(user) or _es_analista(user):
        return True
    return ConfiguracionSistema.get_solo().vendedor_puede_ver_avances


def puede_registrar_pedidos(user):
    """Acceso al módulo Registro Pedidos (alta manual). Admin siempre; analista no
    (es de lectura); vendedor según el flag."""
    if _es_admin(user):
        return True
    if _es_analista(user):
        return False
    return ConfiguracionSistema.get_solo().vendedor_puede_registrar_pedidos


def destino_vendedor(user):
    """URL del primer módulo que el vendedor SÍ puede ver. Se usa como destino seguro
    al bloquear el acceso, evitando bucles de redirección. Si no puede ver nada,
    devuelve la página 'sin acceso'."""
    if _es_admin(user):
        return reverse('core:home')

    # El analista de marketing aterriza en su módulo de Publicidad.
    if _es_marketing(user):
        return reverse('anuncios:dashboard')

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
