"""
Reglas de la gestion de empleados (seccion 3.1.5 de la ERS

el sistema nunca se puede quedar sin un Administrador activo, porque nadie mas podria dar de alta usuarios ni ver Three Dots
"""
from django.contrib.auth.models import Group

from . import roles
from .models import Usuario


class ErrorEmpleados(Exception):
    """error que se le muestra tal cual al Administrador"""


def administradores_activos():
    return Usuario.objects.filter(is_active=True, groups__name=roles.ADMINISTRADOR).distinct()


def asignar_rol(usuario, rol):
    """cada usuario tiene un solo rol, así que se reemplaza el anterior"""
    if rol not in roles.TODOS:
        raise ErrorEmpleados("Ese rol no existe.")
    usuario.groups.set([Group.objects.get_or_create(name=rol)[0]])


def validar_queda_un_administrador(usuario, nuevo_rol=None, desactivar=False):
    """
    lanza ErrorEmpleados si el cambio deja al sistema sin Administradores activos
    se llama antes de quitarle el rol de Administrador a alguien o de desactivarlo
    """
    era_admin = usuario.is_active and usuario.groups.filter(name=roles.ADMINISTRADOR).exists()
    deja_de_ser_admin = desactivar or (nuevo_rol is not None and nuevo_rol != roles.ADMINISTRADOR)
    if era_admin and deja_de_ser_admin and not administradores_activos().exclude(pk=usuario.pk).exists():
        raise ErrorEmpleados("Debe quedar al menos un Administrador activo en el sistema")
