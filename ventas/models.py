from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q


class Venta(models.Model):

    PENDIENTE = "PENDIENTE"
    PAGADA = "PAGADA"
    CANCELADA = "CANCELADA"
    ESTADOS = [
        (PENDIENTE, "Pendiente"),
        (PAGADA, "Pagada"),
        (CANCELADA, "Cancelada"),
    ]

    # RF-VEN-15: solo las ventas cobradas tienen folio, y es unico
    folio = models.PositiveIntegerField("folio", unique=True, null=True, blank=True)
    estado = models.CharField(
        "estado", max_length=10, choices=ESTADOS, default=PENDIENTE, db_index=True
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="cajero",
        on_delete=models.PROTECT,
        related_name="ventas",
    )
    creada = models.DateTimeField("fecha de creación", auto_now_add=True)
    fecha_cobro = models.DateTimeField("fecha y hora de cobro", null=True, blank=True, db_index=True)

    subtotal = models.DecimalField("subtotal", max_digits=12, decimal_places=2, default=Decimal("0.00"))
    descuento = models.DecimalField("descuento", max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField("total", max_digits=12, decimal_places=2, default=Decimal("0.00"))
    impuesto = models.DecimalField(
        "impuesto incluido", max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    monto_recibido = models.DecimalField(
        "monto recibido", max_digits=12, decimal_places=2, null=True, blank=True
    )
    cambio = models.DecimalField("cambio", max_digits=12, decimal_places=2, null=True, blank=True)

    # RF-VEN-17: datos de la cancelacion
    motivo_cancelacion = models.CharField("motivo de cancelación", max_length=200, blank=True)
    cancelada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="cancelada por",
        on_delete=models.PROTECT,
        related_name="ventas_canceladas",
        null=True,
        blank=True,
    )
    fecha_cancelacion = models.DateTimeField("fecha de cancelación", null=True, blank=True)

    class Meta:
        verbose_name = "venta"
        verbose_name_plural = "ventas"
        ordering = ["-creada"]
        constraints = [
            models.CheckConstraint(condition=Q(total__gte=0), name="venta_total_no_negativo"),
            models.CheckConstraint(
                condition=Q(descuento__gte=0) & Q(descuento__lte=models.F("subtotal")),
                name="venta_descuento_valido",
            ),
            # Una venta cobrada siempre tiene folio y fecha de cobro
            models.CheckConstraint(
                condition=Q(estado="PENDIENTE")
                | (Q(folio__isnull=False) & Q(fecha_cobro__isnull=False)),
                name="venta_cobrada_con_folio",
            ),
        ]

    def __str__(self):
        if self.folio:
            return f"Venta {self.folio:06d}"
        return f"Ticket pendiente #{self.pk}"

    @property
    def folio_texto(self):
        """Folio con 6 dígitos para mostrar en el ticket, por ejemplo 000123."""
        return f"{self.folio:06d}" if self.folio else "—"


class DetalleVenta(models.Model):
    """Una línea del ticket: un producto con su cantidad."""

    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name="detalles")
    producto = models.ForeignKey(
        "productos.Producto", on_delete=models.PROTECT, related_name="detalles_venta"
    )
    cantidad = models.PositiveIntegerField("cantidad")
    precio_unitario = models.DecimalField("precio unitario", max_digits=10, decimal_places=2)
    subtotal = models.DecimalField("subtotal", max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = "detalle de venta"
        verbose_name_plural = "detalles de venta"
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["venta", "producto"], name="detalle_producto_unico_por_venta"),
            models.CheckConstraint(condition=Q(cantidad__gt=0), name="detalle_cantidad_mayor_a_cero"),
        ]

    def __str__(self):
        return f"{self.cantidad} x {self.producto}"

    def calcular_subtotal(self):
        self.subtotal = (self.precio_unitario * self.cantidad).quantize(Decimal("0.01"))
        return self.subtotal


class SecuenciaFolio(models.Model):

    ultimo_folio = models.PositiveIntegerField("último folio", default=0)

    class Meta:
        verbose_name = "secuencia de folios"
        verbose_name_plural = "secuencia de folios"

    def __str__(self):
        return f"Último folio: {self.ultimo_folio}"

    @classmethod
    def siguiente(cls):
        secuencia, _ = cls.objects.select_for_update().get_or_create(pk=1)
        secuencia.ultimo_folio += 1
        secuencia.save(update_fields=["ultimo_folio"])
        return secuencia.ultimo_folio
