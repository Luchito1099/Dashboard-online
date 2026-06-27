# productos/models.py
from django.db import models


class Producto(models.Model):
    """Producto del catálogo de Dashboard (cuidado personal / ortopédicos)."""
    nombre = models.CharField(max_length=200)
    sku = models.CharField(max_length=50, blank=True)
    categoria = models.CharField(max_length=100, blank=True)
    orden = models.PositiveSmallIntegerField(default=0)
    activo = models.BooleanField(default=True)

    # Precios
    precio = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    precio_oferta = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    en_oferta = models.BooleanField(default=False)

    # Contenido
    descripcion = models.TextField(blank=True)
    caracteristicas = models.JSONField(default=list, blank=True)   # ["bullet 1", "bullet 2"]

    # Multimedia / enlaces
    # imagen_url = imagen principal de la tarjeta. Los enlaces web ahora viven en LinkProducto.
    imagen_url = models.CharField(max_length=500, blank=True)
    video_url = models.CharField(max_length=500, blank=True)
    link_pago = models.URLField(blank=True)

    class Meta:
        ordering = ['orden', 'nombre']
        verbose_name = 'Producto'
        verbose_name_plural = 'Productos'

    def __str__(self):
        return self.nombre

    @property
    def precio_mostrar(self):
        """Precio vigente: el de oferta si está activa y existe, si no el normal."""
        if self.en_oferta and self.precio_oferta is not None:
            return self.precio_oferta
        return self.precio

    @property
    def tiene_oferta(self):
        return self.en_oferta and self.precio_oferta is not None


class ImagenProducto(models.Model):
    """Imágenes adicionales para la galería del producto."""
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='imagenes')
    url = models.CharField(max_length=500)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['orden']

    def __str__(self):
        return f"Imagen de {self.producto.nombre}"


class ObjecionProducto(models.Model):
    """Objeción frecuente del cliente y su respuesta sugerida (para llamadas en vivo)."""
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='objeciones')
    objecion = models.TextField()
    respuesta = models.TextField()
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['orden']

    def __str__(self):
        return f"{self.producto.nombre}: {self.objecion[:40]}"


class LinkProducto(models.Model):
    """Uno de los varios enlaces web de un producto (página, landing de oferta, etc.)."""
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='links')
    titulo = models.CharField(max_length=120)   # "Página principal", "Landing oferta"
    url = models.URLField()
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['orden']

    def __str__(self):
        return f"{self.producto.nombre}: {self.titulo}"


class ProductoAlias(models.Model):
    """Mapea un nombre/identificador de producto tal como llega de una fuente externa
    (Shopify, Novashop, etc.) al Producto canónico del catálogo. Permite que el mismo
    producto con nombres distintos por tienda se reconozca y se vincule automáticamente
    en la sincronización de pedidos."""
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='alias')
    nombre_externo = models.CharField(max_length=255)
    sku_externo = models.CharField(max_length=120, blank=True)
    external_product_id = models.CharField(max_length=64, blank=True)
    # Tienda/fuente del alias (null = alias global, aplica a cualquier fuente)
    integracion = models.ForeignKey('integraciones.Integracion', on_delete=models.CASCADE,
                                    null=True, blank=True, related_name='alias_productos')
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nombre_externo']
        unique_together = ('integracion', 'nombre_externo')
        verbose_name = 'Alias de producto'
        verbose_name_plural = 'Alias de productos'

    def __str__(self):
        return f'{self.nombre_externo} → {self.producto.nombre}'


class MediaProducto(models.Model):
    """Imagen o video del producto, listo para compartir con el cliente (WhatsApp / copiar link)."""
    TIPO = [('imagen', 'Imagen'), ('video', 'Video')]

    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='medios')
    tipo = models.CharField(max_length=10, choices=TIPO, default='imagen')
    url = models.URLField()
    titulo = models.CharField(max_length=120, blank=True)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['orden']

    def __str__(self):
        return f"{self.producto.nombre}: {self.get_tipo_display()}"
