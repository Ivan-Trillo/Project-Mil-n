"""
Eventos de inicio y cierre de sesión

- Cuentan los intentos fallidos y bloquean la cuenta (RF-AUT-04)
- Registran cada evento en la bitácora (RF-AUD-01)
"""
from datetime import timedelta

from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver
from django.utils import timezone

from auditoria.models import RegistroAuditoria
from auditoria.servicios import registrar

from .models import Usuario

MAX_INTENTOS = 5
MINUTOS_BLOQUEO = 15


@receiver(user_login_failed)
def al_fallar_inicio(sender, credentials, request=None, **kwargs):
    nombre = (credentials or {}).get("username", "")
    usuario = Usuario.objects.filter(username=nombre).first()
    detalle = ""
    if usuario is not None:
        usuario.intentos_fallidos += 1
        if usuario.intentos_fallidos >= MAX_INTENTOS:
            usuario.bloqueado_hasta = timezone.now() + timedelta(minutes=MINUTOS_BLOQUEO)
            usuario.intentos_fallidos = 0
            detalle = f"Cuenta bloqueada {MINUTOS_BLOQUEO} minutos"
        usuario.save(update_fields=["intentos_fallidos", "bloqueado_hasta"])
    registrar(
        request,
        RegistroAuditoria.LOGIN_FALLIDO,
        elemento="Inicio de sesión",
        nuevo=detalle,
        usuario=usuario,
        usuario_texto=nombre,
    )


@receiver(user_logged_in)
def al_iniciar_sesion(sender, request, user, **kwargs):
    if user.intentos_fallidos or user.bloqueado_hasta:
        user.intentos_fallidos = 0
        user.bloqueado_hasta = None
        user.save(update_fields=["intentos_fallidos", "bloqueado_hasta"])
    registrar(request, RegistroAuditoria.LOGIN_OK, elemento="Inicio de sesión", usuario=user)


@receiver(user_logged_out)
def al_cerrar_sesion(sender, request, user, **kwargs):
    if user is not None:
        registrar(request, RegistroAuditoria.LOGOUT, elemento="Cierre de sesión", usuario=user)
