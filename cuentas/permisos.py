"""
control de acceso por rol (RF-AUT-03 y RNF-SEG-05)
cada vista se protege en el servidor, no basta con ocultar la opcion del menu

Uso en vistas de función:
    @rol_requerido(roles.ADMINISTRADOR, roles.ENCARGADO)
    def mi_vista(request): ...

Uso en vistas de clase:
    class MiVista(RolRequeridoMixin, ListView):
        roles_permitidos = (roles.ADMINISTRADOR,)

Con ocultar=True, a quien no tiene permiso se le responde 404 en lugar de 403,
como si la pagina no existiera, asi se protege Three Dots (RF-AUD-05)
"""
from functools import wraps

from django.contrib.auth.mixins import AccessMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import Http404


def _negar(ocultar):
    if ocultar:
        raise Http404
    raise PermissionDenied


def rol_requerido(*roles_permitidos, ocultar=False):
    def decorador(vista):
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            if not request.user.is_authenticated:
                if ocultar:
                    raise Http404
                return redirect_to_login(request.get_full_path())
            if not request.user.tiene_rol(*roles_permitidos):
                _negar(ocultar)
            return vista(request, *args, **kwargs)

        return envoltura

    return decorador


class RolRequeridoMixin(AccessMixin):
    roles_permitidos = ()
    ocultar = False

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            if self.ocultar:
                raise Http404
            return self.handle_no_permission()
        if not request.user.tiene_rol(*self.roles_permitidos):
            _negar(self.ocultar)
        return super().dispatch(request, *args, **kwargs)
