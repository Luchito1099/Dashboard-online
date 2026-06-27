# capacitacion/templatetags/cap_formato.py
"""Filtro que convierte el formato sencillo (markdown-lite) que la admin escribe en
las tareas a HTML seguro para el runbook. Marcadores soportados:

    **texto**        → negrita
    *texto*          → cursiva
    __texto__        → subrayado
    {rojo:texto}     → color (rojo, verde, azul, naranja, morado)

Importante: primero se escapa el texto (para que la admin no pueda inyectar HTML) y
luego se introducen únicamente las etiquetas que controlamos aquí."""
import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()

COLORES = {
    'rojo': '#dc2626',
    'verde': '#16a34a',
    'azul': '#2563eb',
    'naranja': '#ea580c',
    'morado': '#7c3aed',
}

_RE_COLOR = re.compile(r'\{(' + '|'.join(COLORES) + r'):(.+?)\}')


@register.filter
def formato_runbook(texto):
    if not texto:
        return ''
    out = escape(texto)

    out = _RE_COLOR.sub(
        lambda m: f'<span style="color:{COLORES[m.group(1)]}">{m.group(2)}</span>', out)
    out = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', out)   # negrita (antes que cursiva)
    out = re.sub(r'__(.+?)__', r'<u>\1</u>', out)                 # subrayado
    out = re.sub(r'\*(.+?)\*', r'<em>\1</em>', out)               # cursiva

    return mark_safe(out)
