from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from . import roles


class Usuario(AbstractUser):

    #RF-USR-05: cuando el admin restablece la contraseña, el usuario tiene que cambiarla en su siguiente inicio de sesion
    debe_cambiar_password = models.BooleanField(
        "debe cambiar contraseña",
        default=False,
    )

    #RF-AUT-04: despues de 5 intentos fallidos seguidos la cuenta se bloquea 15 minutos
    intentos_fallidos = models.PositiveSmallIntegerField("intentos fallidos", default=0)
    bloqueado_hasta = models.DateTimeField("bloqueado hasta", null=True, blank=True)

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"
        ordering = ["username"]

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def rol(self):
        """Nombre del rol del usuario, o None si no tiene ninguno."""
        grupo = self.groups.first()
        return grupo.name if grupo else None

    def tiene_rol(self, *nombres):
        """True si el usuario pertenece a alguno de los roles indicados."""
        return self.is_active and self.groups.filter(name__in=nombres).exists()

    @property
    def es_administrador(self):
        return self.tiene_rol(roles.ADMINISTRADOR)

    @property
    def es_encargado(self):
        return self.tiene_rol(roles.ENCARGADO)

    @property
    def es_cajero(self):
        return self.tiene_rol(roles.CAJERO)

    @property
    def esta_bloqueado(self):
        return self.bloqueado_hasta is not None and self.bloqueado_hasta > timezone.now()
