# productos/management/commands/seed_productos.py
"""Carga productos reales de KLYNEA (cuidado personal / ortopédicos) con objeciones,
enlaces web múltiples y material compartible (imágenes/videos).
Uso:  python manage.py seed_productos
"""
from django.core.management.base import BaseCommand
from productos.models import Producto, ObjecionProducto, LinkProducto, MediaProducto


# Imagen de marcador de posición (placehold.co genera la imagen al vuelo)
def _img(texto):
    return f"https://placehold.co/600x450/0d1f33/ffffff?text={texto}"


PRODUCTOS = [
    {
        "nombre": "Removedor de callos eléctrico",
        "sku": "KLY-CALLOS-01",
        "categoria": "Cuidado de pies",
        "orden": 1,
        "precio": "89.90",
        "precio_oferta": "59.90",
        "en_oferta": True,
        "descripcion": "Lima eléctrica recargable que elimina callos y durezas de los pies en minutos, "
                       "dejando la piel suave sin esfuerzo. Incluye 3 rodillos de repuesto.",
        "caracteristicas": [
            "Motor recargable por USB, hasta 2 horas de uso",
            "3 rodillos de grano fino, medio y grueso",
            "Cabezal lavable bajo el agua (resistente a salpicaduras)",
            "Apagado automático de seguridad",
        ],
        "imagen_url": _img("Removedor+de+callos"),
        "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "link_pago": "https://pago.klynea.example/callos",
        "links": [
            ("Página principal", "https://klynea.example/removedor-callos"),
            ("Landing de oferta", "https://klynea.example/oferta/callos"),
        ],
        "medios": [
            ("imagen", _img("Callos+frente"), "Foto de frente"),
            ("imagen", _img("Callos+uso"), "Foto en uso"),
            ("video", "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "Video demostración"),
        ],
        "objeciones": [
            ("Es muy caro", "Está en oferta de S/89.90 a S/59.90 e incluye 3 rodillos de repuesto. "
                            "Una pedicura profesional cuesta más y esto te dura años."),
            ("¿Y si me lastima la piel?", "Tiene apagado automático de seguridad y rodillo de grano fino. "
                                          "Empiezas suave; es imposible cortarte como con una cuchilla."),
            ("No sé usarlo", "Es encender y deslizar. Incluye guía y te paso un video de 1 minuto."),
        ],
    },
    {
        "nombre": "Rodillera ortopédica de compresión",
        "sku": "KLY-RODILLA-01",
        "categoria": "Soporte articular",
        "orden": 2,
        "precio": "79.90",
        "precio_oferta": "49.90",
        "en_oferta": True,
        "descripcion": "Rodillera de compresión graduada que estabiliza la articulación, alivia el dolor "
                       "y brinda soporte durante el día o la actividad física. Material transpirable.",
        "caracteristicas": [
            "Compresión graduada que mejora la circulación",
            "Banda de silicona antideslizante",
            "Tejido transpirable, no genera sudor excesivo",
            "Disponible por tallas según contorno de rodilla",
        ],
        "imagen_url": _img("Rodillera+ortopedica"),
        "video_url": "",
        "link_pago": "https://pago.klynea.example/rodillera",
        "links": [
            ("Página principal", "https://klynea.example/rodillera"),
        ],
        "medios": [
            ("imagen", _img("Rodillera+frente"), "Foto de frente"),
            ("imagen", _img("Rodillera+tallas"), "Tabla de tallas"),
        ],
        "objeciones": [
            ("Es muy caro", "Es material médico certificado y trae 30 días de garantía. "
                            "Una sesión de fisioterapia cuesta más que la rodillera completa."),
            ("No sé si me quedará", "Tenemos tabla de tallas exacta. Dime tu contorno de rodilla en cm "
                                    "y te confirmo la talla correcta ahora mismo."),
            ("No me fío de la calidad", "Tejido con compresión graduada y silicona antideslizante. "
                                        "Si no te convence en 30 días, te devolvemos el dinero."),
        ],
    },
    {
        "nombre": "Tobillera de compresión deportiva",
        "sku": "KLY-TOBILLO-01",
        "categoria": "Soporte articular",
        "orden": 3,
        "precio": "54.90",
        "precio_oferta": None,
        "en_oferta": False,
        "descripcion": "Tobillera elástica que sujeta y protege el tobillo ante esguinces, inflamación o "
                       "esfuerzo. Ideal para deporte y recuperación. Se ajusta sin perder movilidad.",
        "caracteristicas": [
            "Sujeción firme sin limitar el movimiento natural",
            "Reduce la inflamación tras esfuerzo o lesión leve",
            "Tela elástica de secado rápido",
            "Uso bajo cualquier calzado",
        ],
        "imagen_url": _img("Tobillera+compresion"),
        "video_url": "",
        "link_pago": "https://pago.klynea.example/tobillera",
        "links": [
            ("Página principal", "https://klynea.example/tobillera"),
        ],
        "medios": [
            ("imagen", _img("Tobillera+frente"), "Foto de frente"),
        ],
        "objeciones": [
            ("¿Sirve para hacer deporte?", "Sí, está diseñada justo para eso: sujeta el tobillo sin quitarte "
                                           "movilidad, ideal para correr o gimnasio."),
            ("¿No se va a estirar y aflojar?", "Tela elástica de alta recuperación que mantiene la compresión "
                                               "lavado tras lavado."),
        ],
    },
    {
        "nombre": "Soporte lumbar / Faja ortopédica",
        "sku": "KLY-LUMBAR-01",
        "categoria": "Soporte de espalda",
        "orden": 4,
        "precio": "119.90",
        "precio_oferta": "89.90",
        "en_oferta": True,
        "descripcion": "Faja lumbar con varillas de soporte que corrige la postura y alivia el dolor de "
                       "espalda baja al cargar peso o estar muchas horas sentado o de pie.",
        "caracteristicas": [
            "Varillas de soporte que estabilizan la zona lumbar",
            "Doble ajuste para compresión personalizada",
            "Alivia dolor por mala postura o carga de peso",
            "Discreta bajo la ropa",
        ],
        "imagen_url": _img("Faja+lumbar"),
        "video_url": "",
        "link_pago": "https://pago.klynea.example/lumbar",
        "links": [
            ("Página principal", "https://klynea.example/faja-lumbar"),
            ("Landing de oferta", "https://klynea.example/oferta/lumbar"),
        ],
        "medios": [
            ("imagen", _img("Faja+frente"), "Foto de frente"),
            ("imagen", _img("Faja+uso"), "Foto en uso"),
        ],
        "objeciones": [
            ("Es muy caro", "Está rebajada a S/89.90 y reemplaza terapias que cuestan mucho más. "
                            "Es una inversión en tu salud postural con 30 días de garantía."),
            ("¿No me dará más calor?", "El material es transpirable y discreto bajo la ropa; está pensado "
                                       "para usarse varias horas sin molestia."),
            ("¿De verdad alivia el dolor?", "Las varillas estabilizan la zona lumbar y corrigen la postura, "
                                            "que es la causa más común del dolor de espalda baja."),
        ],
    },
]


class Command(BaseCommand):
    help = 'Carga los productos iniciales de KLYNEA con objeciones, enlaces y medios.'

    def handle(self, *args, **options):
        # Limpiamos para dejar un estado conocido (objeciones/links/medios caen en cascada)
        Producto.objects.all().delete()

        for datos in PRODUCTOS:
            objeciones = datos.pop('objeciones')
            links = datos.pop('links')
            medios = datos.pop('medios')
            producto = Producto.objects.create(**datos)

            for i, (obj, resp) in enumerate(objeciones):
                ObjecionProducto.objects.create(producto=producto, objecion=obj, respuesta=resp, orden=i)
            for i, (titulo, url) in enumerate(links):
                LinkProducto.objects.create(producto=producto, titulo=titulo, url=url, orden=i)
            for i, (tipo, url, titulo) in enumerate(medios):
                MediaProducto.objects.create(producto=producto, tipo=tipo, url=url, titulo=titulo, orden=i)

            self.stdout.write(
                f'  Producto: {producto.nombre} '
                f'({producto.objeciones.count()} obj, {producto.links.count()} links, {producto.medios.count()} medios)'
            )

        self.stdout.write(self.style.SUCCESS(f'\nListo. {len(PRODUCTOS)} productos cargados.'))
