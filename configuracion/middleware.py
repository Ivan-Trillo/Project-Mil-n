from django.shortcuts import redirect
from django.urls import reverse

from cuentas import roles

from .models import ConfiguracionNegocio


class ConfiguracionInicialMiddleware:
    """
    RF-CFG-04: mientras no exista la configuración del negocio, el admin
    es enviado a esa pantalla, los demas roles pueden seguir trabajando perfectamente
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = getattr(request, "user", None)
        if (
            usuario is not None
            and usuario.is_authenticated
            and not usuario.debe_cambiar_password
            and not request.path.startswith(("/static/", "/media/", "/admin/"))
        ):
            url_config = reverse("configuracion:negocio")
            libres = (url_config, reverse("logout"), reverse("cuentas:cambiar_password"))
            if (
                not request.path.startswith(libres)
                and usuario.tiene_rol(roles.ADMINISTRADOR)
                and ConfiguracionNegocio.obtener() is None
            ):
                return redirect(url_config)
        return self.get_response(request)
