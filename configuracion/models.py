from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class ConfiguracionNegocio(models.Model):
   
    #Datos generales del negocio (sección 3.1.7 y 1.3.1 h de la ERS)

    #solo existe un registro, siempre con id = 1. Para leerlo se usa ConfiguracionNegocio.obtener()

    nombre_comercial = models.CharField("nombre comercial", max_length=120)
    razon_social = models.CharField("razón social", max_length=200, blank=True)
    rfc = models.CharField("RFC", max_length=13, blank=True)
    direccion = models.CharField("dirección", max_length=250, blank=True)
    telefono = models.CharField("teléfono", max_length=20, blank=True)
    # RF-CFG-02: 16 % por defecto los precios ya incluyen el IVA (SUP-03)
    tasa_impuesto = models.DecimalField(
        "tasa de impuesto (%)",
        max_digits=5,
        decimal_places=2,
        default=Decimal("16.00"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    mensaje_ticket = models.CharField(
        "mensaje al pie del ticket",
        max_length=200,
        blank=True,
        default="¡Gracias por su compra!",
    )
    actualizado = models.DateTimeField("última modificación", auto_now=True)

    class Meta:
        verbose_name = "configuración del negocio"
        verbose_name_plural = "configuración del negocio"

    def __str__(self):
        return self.nombre_comercial

    def save(self, *args, **kwargs):
        #siempre se guarda en el mismo registro
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        #la configuracion no se puede borrar
        pass

    @classmethod
    def obtener(cls):
        """Devuelve la configuración, o None si todavía no se ha capturado (RF-CFG-04)."""
        return cls.objects.filter(pk=1).first()
