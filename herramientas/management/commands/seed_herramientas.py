# herramientas/management/commands/seed_herramientas.py
"""Carga herramientas externas de ejemplo del stack Dashboard.
Uso:  python manage.py seed_herramientas
"""
from django.core.management.base import BaseCommand
from herramientas.models import HerramientaExterna

HERRAMIENTAS = [
    {"nombre": "n8n", "icono": "⚙️", "categoria": "Automatización",
     "descripcion": "Automatizaciones y flujos entre apps.", "url": "https://n8n.io", "orden": 1},
    {"nombre": "Chatwoot", "icono": "💬", "categoria": "Atención al cliente",
     "descripcion": "Bandeja unificada de chat y soporte.", "url": "https://www.chatwoot.com", "orden": 2},
    {"nombre": "Shopify", "icono": "🛒", "categoria": "Tienda",
     "descripcion": "Plataforma de ecommerce y pedidos.", "url": "https://www.shopify.com", "orden": 3},
    {"nombre": "Meta Ads", "icono": "📣", "categoria": "Marketing",
     "descripcion": "Gestor de anuncios de Facebook e Instagram.", "url": "https://business.facebook.com", "orden": 4},
    {"nombre": "PostgreSQL Admin", "icono": "🗄️", "categoria": "Infraestructura",
     "descripcion": "Administración de la base de datos (pgAdmin).", "url": "https://www.pgadmin.org", "orden": 5},
    {"nombre": "Coolify", "icono": "🚀", "categoria": "Infraestructura",
     "descripcion": "Panel de despliegue del VPS (self-hosting).", "url": "https://coolify.io", "orden": 6},
]


class Command(BaseCommand):
    help = 'Carga herramientas externas de ejemplo.'

    def handle(self, *args, **options):
        HerramientaExterna.objects.all().delete()
        for datos in HERRAMIENTAS:
            h = HerramientaExterna.objects.create(**datos)
            self.stdout.write(f'  Herramienta: {h.nombre}')
        self.stdout.write(self.style.SUCCESS(f'\nListo. {len(HERRAMIENTAS)} herramientas cargadas.'))
