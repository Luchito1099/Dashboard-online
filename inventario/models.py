# inventario/models.py
"""Inventario por almacén + configuración de reposición. El stock se ajusta a mano y
se descuenta solo cuando un pedido se entrega (ver signals.py). El planificador de
reposición (services.py) cruza el stock con la velocidad de venta y el lead time."""
from django.db import models


class Almacen(models.Model):
    """Un almacén físico. Puede ligarse a una Integración (fuente de pedidos o empresa
    de logística) para que el auto-descuento sepa de dónde restar al entregar un pedido."""
    nombre = models.CharField(max_length=120)
    integracion = models.ForeignKey('integraciones.Integracion', on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='almacenes',
                                    help_text='Fuente o logística que sirve este almacén (para el auto-descuento).')
    es_principal = models.BooleanField(default=False,
                                       help_text='Almacén por defecto cuando un pedido no mapea a otro.')
    activo = models.BooleanField(default=True)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['orden', 'nombre']
        verbose_name = 'Almacén'
        verbose_name_plural = 'Almacenes'

    def __str__(self):
        return self.nombre


class StockProducto(models.Model):
    """Existencias de un producto en un almacén. El stock total de un producto es la
    suma de sus filas en todos los almacenes."""
    producto = models.ForeignKey('productos.Producto', on_delete=models.CASCADE, related_name='stocks')
    # Variante concreta (color/talla…). Null = producto sin variantes.
    variante = models.ForeignKey('productos.VarianteProducto', on_delete=models.CASCADE,
                                 null=True, blank=True, related_name='stocks')
    almacen = models.ForeignKey(Almacen, on_delete=models.CASCADE, related_name='stocks')
    cantidad = models.IntegerField(default=0)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        # Restricciones parciales: a diferencia de unique_together, sí imponen unicidad
        # cuando variante es NULL (Postgres trata los NULL como distintos).
        constraints = [
            models.UniqueConstraint(
                fields=['producto', 'almacen'], condition=models.Q(variante__isnull=True),
                name='uniq_stock_sin_variante'),
            models.UniqueConstraint(
                fields=['producto', 'variante', 'almacen'], condition=models.Q(variante__isnull=False),
                name='uniq_stock_con_variante'),
        ]
        verbose_name = 'Stock por almacén'
        verbose_name_plural = 'Stock por almacén'

    def __str__(self):
        v = f' [{self.variante.nombre}]' if self.variante_id else ''
        return f'{self.producto}{v} @ {self.almacen}: {self.cantidad}'


class MovimientoStock(models.Model):
    """Registro de cada cambio de stock (auditoría). El stock vive en StockProducto;
    aquí queda la traza de cómo llegó a ese número."""
    MOTIVO_AJUSTE = 'ajuste'
    MOTIVO_VENTA = 'venta'
    MOTIVO_IMPORTACION = 'importacion'
    MOTIVO_DEVOLUCION = 'devolucion'
    MOTIVO_CHOICES = [
        (MOTIVO_AJUSTE, 'Ajuste manual'),
        (MOTIVO_VENTA, 'Venta (pedido entregado)'),
        (MOTIVO_IMPORTACION, 'Importación recibida'),
        (MOTIVO_DEVOLUCION, 'Devolución'),
    ]

    producto = models.ForeignKey('productos.Producto', on_delete=models.CASCADE, related_name='movimientos')
    variante = models.ForeignKey('productos.VarianteProducto', on_delete=models.SET_NULL,
                                 null=True, blank=True, related_name='movimientos')
    almacen = models.ForeignKey(Almacen, on_delete=models.CASCADE, related_name='movimientos')
    delta = models.IntegerField(help_text='Positivo suma, negativo resta.')
    motivo = models.CharField(max_length=15, choices=MOTIVO_CHOICES, default=MOTIVO_AJUSTE)
    pedido = models.ForeignKey('integraciones.Pedido', on_delete=models.SET_NULL,
                               null=True, blank=True, related_name='movimientos_stock')
    usuario = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True)
    nota = models.CharField(max_length=255, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-creado']
        verbose_name = 'Movimiento de stock'
        verbose_name_plural = 'Movimientos de stock'

    def __str__(self):
        signo = '+' if self.delta >= 0 else ''
        return f'{signo}{self.delta} {self.producto} @ {self.almacen} ({self.motivo})'


class ConfigReposicion(models.Model):
    """Parámetros de reposición de un producto: el usuario fija el lead time (días que
    demora la importación) y los colchones. Alimenta el planificador."""
    producto = models.OneToOneField('productos.Producto', on_delete=models.CASCADE, related_name='reposicion')
    dias_entrega = models.PositiveSmallIntegerField(default=30,
                                                    help_text='Días que demora una importación en llegar (lead time).')
    dias_seguridad = models.PositiveSmallIntegerField(default=7,
                                                      help_text='Colchón extra antes de quedarte sin stock.')
    dias_cobertura = models.PositiveSmallIntegerField(default=60,
                                                      help_text='Cuántos días de venta quieres cubrir al comprar (para la cantidad sugerida).')
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Configuración de reposición'
        verbose_name_plural = 'Configuración de reposición'

    def __str__(self):
        return f'Reposición de {self.producto} (lead {self.dias_entrega}d)'
