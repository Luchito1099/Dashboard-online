# capacitacion/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponseNotAllowed
from django.urls import reverse
from django.db.models import Max
from django.utils import timezone
from .models import Tarea, Bloque, BloqueTarea, ProgresoTarea, Estrategia


# ───────────────────────── Datos estáticos (no necesitan BD) ─────────────────────────

GLOSARIO = [
    {"t": "CRM", "d": "Sistema de gestión de clientes"},
    {"t": "KPI", "d": "Indicador clave de rendimiento"},
    {"t": "Ticket", "d": "Monto promedio por pedido"},
    {"t": "Carrito", "d": "Productos sin completar = oportunidad"},
    {"t": "Courier", "d": "Empresa de mensajería"},
    {"t": "ETA", "d": "Fecha/hora estimada de entrega"},
    {"t": "VIP", "d": "Cliente frecuente o de alto valor"},
    {"t": "Inactivo", "d": "Sin compra en 30+ días"},
    {"t": "Conversión", "d": "Llamada que resulta en venta"},
]

REGLAS = [
    "Si un cliente está enojado, escucha primero, soluciona después.",
    "Toda promesa al cliente debe quedar en el CRM. Si no está escrito, no existe.",
    "Quiebre de stock: notifica en menos de 2 horas.",
    "Corte logístico a las 16:00 — después, despacho al día siguiente.",
    "Si el caso escala, transfiere al supervisor de inmediato.",
    "Cierra cada llamada con un próximo paso claro.",
]


# ───────────────────────── Helpers de permisos ─────────────────────────

def es_admin(user):
    """True si el usuario es superuser o tiene rol 'admin' en su Perfil.
    Se usa hasattr para no romper con usuarios que aún no tienen Perfil asociado."""
    if user.is_superuser:
        return True
    return hasattr(user, 'perfil') and user.perfil.rol == 'admin'


def es_analista(user):
    """True si el usuario tiene rol 'analista' en su Perfil (el superuser es admin,
    no analista). El analista ve todo en lectura y los Avances completos."""
    return hasattr(user, 'perfil') and user.perfil.rol == 'analista'


def tareas_completadas_hoy(user):
    """IDs de las tareas que el usuario marcó como completadas el día de hoy."""
    hoy = timezone.now().date()
    return set(
        ProgresoTarea.objects.filter(
            usuario=user, fecha=hoy, completada=True
        ).values_list('tarea_id', flat=True)
    )


def calcular_porcentaje(done, total):
    """Porcentaje entero de avance (evita división por cero)."""
    return round(done / total * 100) if total else 0


# ───────────────────────── Vistas ─────────────────────────

@login_required
def index(request):
    """Runbook diario: embudo, timeline de bloques y sidebar con tabs."""
    # Permiso configurable: el vendedor solo entra si está habilitado (admin siempre)
    from core.permisos import puede_ver, destino_vendedor
    if not puede_ver(request.user, 'vendedor_puede_ver_capacitacion'):
        messages.error(request, 'No tienes permisos para ver la capacitación.')
        return redirect(destino_vendedor(request.user))

    # Bloques con sus tareas en una sola consulta (evita N+1)
    bloques = (
        Bloque.objects
        .prefetch_related('bloquearea_set__tarea')
        .order_by('orden')
    )

    completadas = tareas_completadas_hoy(request.user)
    tareas = Tarea.objects.filter(activo=True)
    total = tareas.count()
    done = len(completadas)

    # Datos de tareas para el JS (embudo, sidebar de alerta, mini-lista).
    # Se serializan con json_script en la plantilla.
    tareas_data = [
        {
            'id': t.id,
            'nombre': t.nombre,
            'hora': t.hora,
            'mins': t.mins,
            'tipo': t.tipo,
            'prioridad': t.prioridad,
            'flexible': t.flexible,
            'completada': t.id in completadas,
        }
        for t in tareas.order_by('mins')
    ]

    context = {
        'bloques': bloques,
        # Lista (no set) para que json_script pueda serializarla; el "in" del template funciona igual
        'completadas': list(completadas),
        'total': total,
        'done': done,
        'porcentaje': calcular_porcentaje(done, total),
        'puede_editar': es_admin(request.user),
        'tareas_data': tareas_data,
        'glosario': GLOSARIO,
        'reglas': REGLAS,
    }
    return render(request, 'capacitacion/index.html', context)


@login_required
def toggle_tarea(request, tarea_id):
    """Marca/desmarca una tarea como completada para hoy.
    Devuelve JSON {completada, done, total, porcentaje} para actualizar la UI sin recargar."""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    hoy = timezone.now().date()
    tarea = get_object_or_404(Tarea, id=tarea_id)

    progreso, creado = ProgresoTarea.objects.get_or_create(
        usuario=request.user,
        tarea=tarea,
        fecha=hoy,
        defaults={'completada': True},
    )
    # Si ya existía, invertimos el estado (toggle)
    if not creado:
        progreso.completada = not progreso.completada
        progreso.save()

    # Recalculamos el progreso global del día para devolverlo al front
    done = len(tareas_completadas_hoy(request.user))
    total = Tarea.objects.filter(activo=True).count()

    return JsonResponse({
        'completada': progreso.completada,
        'done': done,
        'total': total,
        'porcentaje': calcular_porcentaje(done, total),
    })


@login_required
def admin_panel(request):
    """Panel de administración del runbook: lista todas las tareas para editarlas.
    Solo accesible para admin/superuser; un vendedor es redirigido al inicio."""
    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos para administrar tareas.')
        return redirect('capacitacion:index')

    tareas = Tarea.objects.all().order_by('orden', 'mins')
    context = {
        'tareas': tareas,
        'bloques': Bloque.objects.order_by('orden'),
        'prioridades': Tarea.PRIORIDAD_CHOICES,
        'tipos': Tarea.TIPO_CHOICES,
    }
    return render(request, 'capacitacion/admin.html', context)


@login_required
def crear_tarea(request):
    """Crea una tarea nueva con los datos básicos y la vincula a un bloque (para que
    aparezca en el runbook). Luego redirige al admin para completar el resto. Solo admin (POST)."""
    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos para crear tareas.')
        return redirect('capacitacion:index')
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    nombre = request.POST.get('nombre', '').strip() or 'Tarea nueva'
    hora = request.POST.get('hora', '08:00').strip()
    tipo = request.POST.get('tipo', Tarea.TIPO_CHOICES[0][0])
    prioridad = request.POST.get('prioridad', 'media')

    # Orden = el siguiente disponible; mins se deriva de la hora
    siguiente_orden = (Tarea.objects.aggregate(m=Max('orden'))['m'] or 0) + 1
    tarea = Tarea.objects.create(
        nombre=nombre,
        hora=hora,
        mins=_hora_a_minutos(hora, 480),
        tipo=tipo,
        prioridad=prioridad,
        orden=siguiente_orden,
        descripcion='',
        pasos=[],
        tips=[],
        habilidades=[],
    )

    # Vinculamos la tarea al bloque elegido para que se vea en el runbook
    bloque = Bloque.objects.filter(id=request.POST.get('bloque')).first()
    if bloque:
        orden_bt = BloqueTarea.objects.filter(bloque=bloque).count()
        BloqueTarea.objects.create(bloque=bloque, tarea=tarea, orden=orden_bt)

    messages.success(request, f'Tarea «{nombre}» creada. Completa sus detalles abajo.')
    # Volvemos al admin con el ancla puesta en la tarea recién creada
    return redirect(reverse('capacitacion:admin_panel') + f'#tarea-{tarea.id}')


@login_required
def editar_tarea(request, tarea_id):
    """Guarda los cambios de una tarea enviados desde el panel admin (POST).
    Solo admin/superuser. Los pasos llegan uno por línea; los tips como 'tipo|texto'."""
    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos para editar tareas.')
        return redirect('capacitacion:index')

    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    tarea = get_object_or_404(Tarea, id=tarea_id)

    # Campos simples
    tarea.nombre = request.POST.get('nombre', tarea.nombre).strip()
    tarea.hora = request.POST.get('hora', tarea.hora).strip()
    tarea.tipo = request.POST.get('tipo', tarea.tipo)
    tarea.prioridad = request.POST.get('prioridad', tarea.prioridad)
    tarea.descripcion = request.POST.get('descripcion', tarea.descripcion).strip()

    # "mins" se recalcula desde "hora" (HH:MM) para mantener coherente la línea de tiempo
    tarea.mins = _hora_a_minutos(tarea.hora, tarea.mins)

    # Pasos: una línea = un paso (se ignoran líneas vacías)
    pasos_raw = request.POST.get('pasos', '')
    tarea.pasos = [p.strip() for p in pasos_raw.splitlines() if p.strip()]

    # Tips: cada línea con formato "tipo|texto" (tipo = tip | warn | info)
    tips_raw = request.POST.get('tips', '')
    tarea.tips = _parsear_tips(tips_raw)

    tarea.save()
    messages.success(request, f'Tarea «{tarea.nombre}» actualizada.')
    return redirect('capacitacion:admin_panel')


@login_required
def eliminar_tarea(request, tarea_id):
    """Elimina una tarea del runbook. Solo admin/superuser (POST).
    Los vínculos a bloques (BloqueTarea) y el progreso (ProgresoTarea) se borran en cascada."""
    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos para eliminar tareas.')
        return redirect('capacitacion:index')
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    tarea = get_object_or_404(Tarea, id=tarea_id)
    nombre = tarea.nombre
    tarea.delete()
    messages.success(request, f'Tarea «{nombre}» eliminada.')
    return redirect('capacitacion:admin_panel')


# ───────────────────────── Bloques (solo admin) ─────────────────────────

@login_required
def crear_bloque(request):
    """Crea un nuevo bloque de tareas. Solo admin/superuser (POST)."""
    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos para administrar bloques.')
        return redirect('capacitacion:index')
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    label = request.POST.get('label', '').strip()
    if not label:
        messages.error(request, 'El nombre del bloque es obligatorio.')
        return redirect('capacitacion:admin_panel')
    # El label es único: evitamos duplicados
    if Bloque.objects.filter(label=label).exists():
        messages.error(request, f'Ya existe un bloque llamado «{label}».')
        return redirect('capacitacion:admin_panel')

    orden = _a_entero(request.POST.get('orden'), Bloque.objects.count())
    Bloque.objects.create(label=label, orden=orden)
    messages.success(request, f'Bloque «{label}» creado.')
    return redirect('capacitacion:admin_panel')


@login_required
def editar_bloque(request, bloque_id):
    """Modifica el nombre (label) y el orden de un bloque. Solo admin/superuser (POST)."""
    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos para editar bloques.')
        return redirect('capacitacion:index')
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    bloque = get_object_or_404(Bloque, id=bloque_id)
    label = request.POST.get('label', '').strip()
    if not label:
        messages.error(request, 'El nombre del bloque es obligatorio.')
        return redirect('capacitacion:admin_panel')
    # Validamos unicidad del label contra los demás bloques
    if Bloque.objects.filter(label=label).exclude(id=bloque.id).exists():
        messages.error(request, f'Ya existe otro bloque llamado «{label}».')
        return redirect('capacitacion:admin_panel')

    bloque.label = label
    bloque.orden = _a_entero(request.POST.get('orden'), bloque.orden)
    bloque.save()
    messages.success(request, f'Bloque «{label}» actualizado.')
    return redirect('capacitacion:admin_panel')


# ───────────────────────── Utilidades internas ─────────────────────────

def _a_entero(valor, por_defecto):
    """Convierte un string a entero; si está vacío o falla, devuelve el valor por defecto."""
    try:
        return int(valor)
    except (ValueError, TypeError):
        return por_defecto

def _hora_a_minutos(hora, por_defecto):
    """Convierte 'HH:MM' a minutos desde medianoche. Si falla, devuelve el valor previo."""
    try:
        h, m = hora.split(':')
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return por_defecto


def _parsear_tips(texto):
    """Convierte un textarea de tips a la estructura [{'k': tipo, 't': texto}].
    Formato por línea: 'tipo|texto'. Si no hay '|', se asume tipo 'info'."""
    tips = []
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea:
            continue
        if '|' in linea:
            tipo, txt = linea.split('|', 1)
            tipo = tipo.strip().lower()
            if tipo not in ('tip', 'warn', 'info'):
                tipo = 'info'
            tips.append({'k': tipo, 't': txt.strip()})
        else:
            tips.append({'k': 'info', 't': linea})
    return tips


# ───────────────────────── Estrategias (catálogo) ─────────────────────────

@login_required
def estrategias(request):
    """Catálogo de estrategias de venta. Visible para quien puede ver capacitación."""
    from core.permisos import puede_ver, destino_vendedor
    if not puede_ver(request.user, 'vendedor_puede_ver_capacitacion'):
        messages.error(request, 'No tienes permisos para ver las estrategias.')
        return redirect(destino_vendedor(request.user))

    context = {
        'estrategias': Estrategia.objects.filter(activo=True),
        'puede_editar': es_admin(request.user),
    }
    return render(request, 'capacitacion/estrategias.html', context)


@login_required
def estrategias_admin(request):
    """Lista editable de estrategias. Solo admin."""
    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos para administrar estrategias.')
        return redirect('capacitacion:estrategias')
    return render(request, 'capacitacion/estrategias_admin.html',
                  {'estrategias': Estrategia.objects.all()})


@login_required
def crear_estrategia(request):
    """Crea una estrategia vacía para completarla. Solo admin (POST)."""
    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos para crear estrategias.')
        return redirect('capacitacion:estrategias')
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    Estrategia.objects.create(nombre='Nueva estrategia', orden=Estrategia.objects.count() + 1)
    messages.success(request, 'Estrategia creada. Edítala abajo.')
    return redirect('capacitacion:estrategias_admin')


@login_required
def editar_estrategia(request, estrategia_id):
    """Guarda los cambios de una estrategia. Solo admin (POST)."""
    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos para editar estrategias.')
        return redirect('capacitacion:estrategias')
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    e = get_object_or_404(Estrategia, id=estrategia_id)
    e.nombre = request.POST.get('nombre', e.nombre).strip() or e.nombre
    e.descripcion = request.POST.get('descripcion', e.descripcion).strip()
    e.icono = request.POST.get('icono', e.icono).strip()
    e.activo = request.POST.get('activo') == 'on'
    e.save()
    messages.success(request, f'Estrategia «{e.nombre}» actualizada.')
    return redirect('capacitacion:estrategias_admin')


@login_required
def eliminar_estrategia(request, estrategia_id):
    """Elimina una estrategia. Solo admin (POST)."""
    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos para eliminar estrategias.')
        return redirect('capacitacion:estrategias')
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    e = get_object_or_404(Estrategia, id=estrategia_id)
    nombre = e.nombre
    e.delete()
    messages.success(request, f'Estrategia «{nombre}» eliminada.')
    return redirect('capacitacion:estrategias_admin')
