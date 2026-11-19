"""
Opciones de navegación (RNF-INT-02)

MENU es la barra superior MENU_CUENTA son las opciones del menu del avatar
Cada opcion dice que roles la pueden ver el menu solo muestra lo que el rol del
usuario tiene permitido, pero la proteccion real está en cada vista (RNF-SEG-05)

Si una ruta todavia no existe (porque su modulo no está programado), la opción
aparece deshabilitada en lugar de romper la pagina
"""
from django.urls import NoReverseMatch, reverse

from cuentas import roles

SOLO_ADMIN = (roles.ADMINISTRADOR,)

#nombre de la ruta, texto, icono de Bootstrap Icons, roles que la ven
MENU = [
    ("ventas:caja", "Caja", "bi-cart3", roles.TODOS),
    ("productos:catalogo", "Inventario", "bi-box-seam", roles.TODOS),
    ("ventas:historial", "Registro", "bi-receipt", roles.GESTION),
    ("cuentas:usuarios", "Empleados", "bi-people", SOLO_ADMIN),
    ("proveedores:lista", "Proveedores", "bi-truck", roles.GESTION),
    ("panel:inicio", "Dashboard", "bi-graph-up", roles.GESTION),
]

MENU_CUENTA = [
    ("cuentas:cambiar_password", "Cambiar contraseña", "bi-key", roles.TODOS),
    ("configuracion:negocio", "Configuración del negocio", "bi-gear", SOLO_ADMIN),
    ("auditoria:bitacora", "Three Dots", "bi-three-dots", SOLO_ADMIN),
]


def _construir(definicion, nombres_roles, ruta_actual):
    opciones = []
    for ruta, texto, icono, permitidos in definicion:
        if not nombres_roles.intersection(permitidos):
            continue
        try:
            url = reverse(ruta)
        except NoReverseMatch:
            url = None
        opciones.append({
            "texto": texto,
            "icono": icono,
            "url": url,
            "activa": bool(url) and ruta_actual.startswith(url),
        })
    return opciones


def opciones_para(usuario, ruta_actual=""):
    if not usuario.is_authenticated:
        return [], []
    nombres_roles = set(usuario.groups.values_list("name", flat=True))
    return (
        _construir(MENU, nombres_roles, ruta_actual),
        _construir(MENU_CUENTA, nombres_roles, ruta_actual),
    )
