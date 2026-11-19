"""
Registro de eventos en la bitácora Three Dots (RF-AUD-01 y RF-AUD-02).

Desde cualquier vista:

    from auditoria.servicios import registrar
    registrar(request, RegistroAuditoria.CAMBIO_PRECIO, elemento=producto,
              anterior="20.00", nuevo="25.00")
"""
from .models import RegistroAuditoria


def obtener_ip(request):
    if request is None:
        return None
    return request.META.get("REMOTE_ADDR") or None


def registrar(request, accion, elemento="", anterior="", nuevo="", usuario=None, usuario_texto=""):
    if usuario is None and request is not None and request.user.is_authenticated:
        usuario = request.user
    return RegistroAuditoria.objects.create(
        usuario=usuario,
        usuario_texto=usuario_texto or (usuario.username if usuario else ""),
        accion=accion,
        elemento=str(elemento)[:200],
        valor_anterior="" if anterior is None else str(anterior),
        valor_nuevo="" if nuevo is None else str(nuevo),
        ip=obtener_ip(request),
    )
