from django.conf import settings
from django.db import models


class RegistroAuditoria(models.Model):
    """
    Un evento de la bitácora Three Dots (RF-AUD-01 y RF-AUD-02).

    Los registros solo se crean, nunca se editan ni se borran (RF-AUD-04).
    """

    LOGIN_OK = "LOGIN_OK"
    LOGIN_FALLIDO = "LOGIN_FALLIDO"
    LOGOUT = "LOGOUT"
    PRODUCTO_ALTA = "PRODUCTO_ALTA"
    PRODUCTO_EDICION = "PRODUCTO_EDICION"
    PRODUCTO_BAJA = "PRODUCTO_BAJA"
    CAMBIO_PRECIO = "CAMBIO_PRECIO"
    INVENTARIO_AJUSTE = "INVENTARIO_AJUSTE"
    VENTA_CANCELACION = "VENTA_CANCELACION"
    CONFIGURACION = "CONFIGURACION"
    USUARIO_ALTA = "USUARIO_ALTA"
    USUARIO_EDICION = "USUARIO_EDICION"
    USUARIO_ESTADO = "USUARIO_ESTADO"
    USUARIO_PASSWORD = "USUARIO_PASSWORD"
    PROVEEDOR_ALTA = "PROVEEDOR_ALTA"
    PROVEEDOR_EDICION = "PROVEEDOR_EDICION"
    PROVEEDOR_ESTADO = "PROVEEDOR_ESTADO"
    VENTA_DESCUENTO = "VENTA_DESCUENTO"
    ACCIONES = [
        (LOGIN_OK, "Inicio de sesión"),
        (LOGIN_FALLIDO, "Inicio de sesión fallido"),
        (LOGOUT, "Cierre de sesión"),
        (PRODUCTO_ALTA, "Alta de producto"),
        (PRODUCTO_EDICION, "Edición de producto"),
        (PRODUCTO_BAJA, "Baja de producto"),
        (CAMBIO_PRECIO, "Cambio de precio"),
        (INVENTARIO_AJUSTE, "Entrada o ajuste de inventario"),
        (VENTA_CANCELACION, "Cancelación de venta"),
        (CONFIGURACION, "Cambio de configuración"),
        (USUARIO_ALTA, "Alta de usuario"),
        (USUARIO_EDICION, "Edición de usuario"),
        (USUARIO_ESTADO, "Activación o desactivación de usuario"),
        (USUARIO_PASSWORD, "Restablecimiento de contraseña"),
        (PROVEEDOR_ALTA, "Alta de proveedor"),
        (PROVEEDOR_EDICION, "Edición de proveedor"),
        (PROVEEDOR_ESTADO, "Activación o desactivación de proveedor"),
        (VENTA_DESCUENTO, "Venta con descuento"),
    ]

    fecha = models.DateTimeField("fecha y hora", auto_now_add=True, db_index=True)
    #puede ser null en un login fallido con un usuario que no existe
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="registros_auditoria",
        null=True,
        blank=True,
    )
    usuario_texto = models.CharField(
        "usuario escrito", max_length=150, blank=True,
        help_text="Nombre de usuario tal como se escribió, útil en los intentos fallidos",
    )
    accion = models.CharField("acción", max_length=20, choices=ACCIONES, db_index=True)
    elemento = models.CharField("elemento afectado", max_length=200, blank=True)
    valor_anterior = models.TextField("valor anterior", blank=True)
    valor_nuevo = models.TextField("valor nuevo", blank=True)
    ip = models.GenericIPAddressField("dirección IP", null=True, blank=True)

    class Meta:
        verbose_name = "registro de auditoría"
        verbose_name_plural = "registros de auditoría"
        ordering = ["-fecha"]

    #agrupacion de acciones para los filtros
    CATEGORIAS = [
        ("sesiones", "Sesiones", "bi-box-arrow-in-right", (LOGIN_OK, LOGIN_FALLIDO, LOGOUT)),
        ("productos", "Productos e inventario", "bi-box-seam",
         (PRODUCTO_ALTA, PRODUCTO_EDICION, PRODUCTO_BAJA, CAMBIO_PRECIO, INVENTARIO_AJUSTE)),
        ("ventas", "Ventas", "bi-receipt", (VENTA_CANCELACION, VENTA_DESCUENTO)),
        ("proveedores", "Proveedores", "bi-truck", (PROVEEDOR_ALTA, PROVEEDOR_EDICION, PROVEEDOR_ESTADO)),
        ("usuarios", "Empleados", "bi-people", (USUARIO_ALTA, USUARIO_EDICION, USUARIO_ESTADO, USUARIO_PASSWORD)),
        ("configuracion", "Configuración", "bi-gear", (CONFIGURACION,)),
    ]
    #acciones pendientes a revisar
    ALERTAS = (LOGIN_FALLIDO, VENTA_CANCELACION, VENTA_DESCUENTO, CAMBIO_PRECIO, USUARIO_PASSWORD)

    def __str__(self):
        return f"{self.fecha:%d/%m/%Y %H:%M} {self.get_accion_display()}"

    @classmethod
    def acciones_de(cls, categoria):
        for clave, _, _, acciones in cls.CATEGORIAS:
            if clave == categoria:
                return acciones
        return ()

    @property
    def icono(self):
        for _, _, icono, acciones in self.CATEGORIAS:
            if self.accion in acciones:
                return icono
        return "bi-dot"

    @property
    def es_alerta(self):
        return self.accion in self.ALERTAS

    @property
    def tiene_detalle(self):
        return bool(self.valor_anterior or self.valor_nuevo)
