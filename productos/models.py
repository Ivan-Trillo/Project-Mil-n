from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q


class Categoria(models.Model):
    #Agrupación de productos (RF-PRO-07) no se borra solo se desactiva

    nombre = models.CharField("nombre", max_length=80, unique=True)
    activa = models.BooleanField("activa", default=True)

    class Meta:
        verbose_name = "categoría"
        verbose_name_plural = "categorías"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Proveedor(models.Model):
    #Proveedor de mercancia no se borra solo se desactiva

    nombre = models.CharField("nombre", max_length=150, unique=True)
    contacto = models.CharField("persona de contacto", max_length=120, blank=True)
    telefono = models.CharField("teléfono", max_length=20, blank=True)
    correo = models.EmailField("correo electrónico", blank=True)
    rfc = models.CharField("RFC", max_length=13, blank=True)
    notas = models.TextField("notas", blank=True)
    activo = models.BooleanField("activo", default=True)
    creado = models.DateTimeField("fecha de alta", auto_now_add=True)

    class Meta:
        verbose_name = "proveedor"
        verbose_name_plural = "proveedores"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


def ruta_imagen_producto(instancia, nombre_archivo):
    """Guarda las fotos en media/productos/<sku>.<extensión>"""
    extension = nombre_archivo.rsplit(".", 1)[-1].lower()
    return f"productos/{instancia.sku}.{extension}"


class Producto(models.Model):
    """
    Articulo a la venta (RF-PRO-01)

    Las reglas de RNF-BD-01 y RNF-BD-02 tambien se validan en la base de datos,
    asi aunque falle una validacion del formulario, PostgreSQL no deja guardar
    datos inválidos
    """

    codigo_barras = models.CharField(
        "código de barras", max_length=50, unique=True, null=True, blank=True
    )
    sku = models.CharField("SKU", max_length=50, unique=True)
    nombre = models.CharField("nombre", max_length=150, db_index=True)
    descripcion = models.TextField("descripción", blank=True)
    categoria = models.ForeignKey(
        Categoria,
        verbose_name="categoría",
        on_delete=models.PROTECT,
        related_name="productos",
        null=True,
        blank=True,
    )
    proveedor = models.ForeignKey(
        Proveedor,
        verbose_name="proveedor",
        on_delete=models.PROTECT,
        related_name="productos",
        null=True,
        blank=True,
    )
    imagen = models.ImageField("foto", upload_to=ruta_imagen_producto, blank=True)
    #RNF-BD-03: los importes siempre como decimales exactos
    precio_venta = models.DecimalField(
        "precio de venta",
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    costo = models.DecimalField(
        "costo",
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    existencia = models.IntegerField("existencia", default=0)
    existencia_minima = models.IntegerField("existencia mínima", default=0)
    activo = models.BooleanField("activo", default=True)
    creado = models.DateTimeField("fecha de alta", auto_now_add=True)
    actualizado = models.DateTimeField("última modificación", auto_now=True)

    class Meta:
        verbose_name = "producto"
        verbose_name_plural = "productos"
        ordering = ["nombre"]
        constraints = [
            models.CheckConstraint(
                condition=Q(precio_venta__gt=0),
                name="producto_precio_mayor_a_cero",
            ),
            models.CheckConstraint(
                condition=Q(costo__gte=0),
                name="producto_costo_no_negativo",
            ),
            #RNF-CON-03: aunque dos cobros pasen al mismo tiempo,
            #PostgreSQL nunca deja la existencia en negativo
            models.CheckConstraint(
                condition=Q(existencia__gte=0),
                name="producto_existencia_no_negativa",
            ),
            models.CheckConstraint(
                condition=Q(existencia_minima__gte=0),
                name="producto_minimo_no_negativo",
            ),
        ]

    def __str__(self):
        return self.nombre

    @property
    def existencia_baja(self):
        #RF-PRO-10: existencia igual o menor al minimo
        return self.existencia <= self.existencia_minima

    @classmethod
    def con_existencia_baja(cls):
        #Productos activos con existencia igual o menor a su minimo (RF-DAS-03)
        return cls.objects.filter(activo=True, existencia__lte=F("existencia_minima"))


class MovimientoInventario(models.Model):
#Cada cambio en la existencia de un producto (RF-PRO-08 y RF-PRO-09) la cantidad es positiva cuando entra mercancia y negativa cuando sale

    VENTA = "VENTA"
    ENTRADA = "ENTRADA"
    AJUSTE = "AJUSTE"
    CANCELACION = "CANCELACION"
    TIPOS = [
        (VENTA, "Venta"),
        (ENTRADA, "Entrada"),
        (AJUSTE, "Ajuste"),
        (CANCELACION, "Cancelación de venta"),
    ]

    producto = models.ForeignKey(
        Producto, on_delete=models.PROTECT, related_name="movimientos"
    )
    tipo = models.CharField("tipo", max_length=12, choices=TIPOS)
    cantidad = models.IntegerField("cantidad")
    existencia_resultante = models.IntegerField("existencia resultante")
    motivo = models.CharField("motivo", max_length=200, blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="movimientos_inventario",
    )
    #si el movimiento viene de una venta o de su cancelación
    venta = models.ForeignKey(
        "ventas.Venta",
        on_delete=models.PROTECT,
        related_name="movimientos",
        null=True,
        blank=True,
    )
    fecha = models.DateTimeField("fecha y hora", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "movimiento de inventario"
        verbose_name_plural = "movimientos de inventario"
        ordering = ["-fecha"]
        constraints = [
            models.CheckConstraint(
                condition=~Q(cantidad=0),
                name="movimiento_cantidad_distinta_de_cero",
            ),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} {self.cantidad:+d} de {self.producto}"
