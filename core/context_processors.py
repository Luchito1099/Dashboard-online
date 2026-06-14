# core/context_processors.py
"""Context processor que inyecta el resumen del runbook en todas las plantillas.
Así el panel derecho de base.html puede mostrar próxima tarea y progreso en cualquier página."""
from django.utils import timezone

from capacitacion.models import Tarea, ProgresoTarea
from capacitacion.views import es_admin


def runbook(request):
    # Solo tiene sentido para usuarios autenticados
    if not request.user.is_authenticated:
        return {}

    hoy = timezone.now().date()
    tareas = Tarea.objects.filter(activo=True)
    total = tareas.count()

    completadas = set(
        ProgresoTarea.objects.filter(
            usuario=request.user, fecha=hoy, completada=True
        ).values_list('tarea_id', flat=True)
    )
    done = len(completadas)

    # Próxima tarea = primera tarea activa del día que aún no está completada
    proxima = tareas.exclude(id__in=completadas).first()

    return {
        'rb_total': total,
        'rb_done': done,
        'rb_proxima': proxima,
        'puede_editar': es_admin(request.user),
    }
