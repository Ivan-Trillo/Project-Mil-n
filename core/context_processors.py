from pathlib import Path

from django.conf import settings

from configuracion.models import ConfiguracionNegocio

from .menu import opciones_para

CARPETAS_ESTATICAS = [Path(settings.BASE_DIR) / "static" / "css", Path(settings.BASE_DIR) / "static" / "js"]


def version_estaticos():
    """
    Número que cambia cada vez que se modifica un CSS o JS propio. Se agrega a las
    URL (?v=...) para que el navegador no use una copia vieja guardada en caché.
    """
    try:
        return str(int(max(
            archivo.stat().st_mtime
            for carpeta in CARPETAS_ESTATICAS
            for archivo in carpeta.glob("*")
            if archivo.is_file()
        )))
    except ValueError:
        return "1"


def sistema(request):
    """Datos disponibles en todas las plantillas."""
    datos = {"v": version_estaticos()}
    usuario = getattr(request, "user", None)
    if usuario is None:
        return datos
    menu, menu_cuenta = opciones_para(usuario, request.path)
    datos.update({
        "menu": menu,
        "menu_cuenta": menu_cuenta,
        "negocio": ConfiguracionNegocio.obtener() if usuario.is_authenticated else None,
    })
    return datos
