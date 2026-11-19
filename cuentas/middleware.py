from django.shortcuts import redirect
from django.urls import reverse


class CambioPasswordObligatorioMiddleware:
    """
    RF-USR-05: si el Administrador restablecio la contraseña de un usuario,
    ese usuario no puede usar el sistema hasta que la cambie
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = getattr(request, "user", None)
        if usuario is not None and usuario.is_authenticated and usuario.debe_cambiar_password:
            permitidas = (
                reverse("cuentas:cambiar_password"),
                reverse("logout"),
            )
            if not request.path.startswith(permitidas) and not request.path.startswith(("/static/", "/media/")):
                return redirect("cuentas:cambiar_password")
        return self.get_response(request)
