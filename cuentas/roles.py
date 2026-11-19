"""
Roles del sistema (sección 1.3.3 de la ERS)

Los roles se guardan como grupos de Django se crean automaticamente con la
migración 0002_crear_roles, así que no hay que darlos de alta a mano
"""

ADMINISTRADOR = "Administrador"
ENCARGADO = "Encargado"
CAJERO = "Cajero"

TODOS = (ADMINISTRADOR, ENCARGADO, CAJERO)
GESTION = (ADMINISTRADOR, ENCARGADO)  # pueden administrar productos y ver ventas
