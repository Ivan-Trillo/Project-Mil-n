"""
logica del inventario que usan varios modulos

toda modificacion de existencias pasa por registrar_movimiento(), asi siempre
queda el historial (RF-PRO-09) y nunca se deja la existencia en negativo
(RNF-CON-01 y RNF-CON-03)
"""
from django.db import transaction
from django.db.models import F

from .models import MovimientoInventario, Producto


class ExistenciaInsuficiente(Exception):
    #La operacion dejaria la existencia del producto en negativo

    def __init__(self, producto, disponible, solicitado):
        self.producto = producto
        self.disponible = disponible
        self.solicitado = solicitado
        super().__init__(
            f"No hay suficiente existencia de {producto}: hay {disponible} y se necesitan {solicitado}"
        )


@transaction.atomic
def registrar_movimiento(producto, tipo, cantidad, usuario, motivo="", venta=None):
    """
    suma (cantidad positiva) o resta (cantidad negativa) existencias de un producto
    y guarda el movimiento bloquea la fila del producto mientras dura la operación,
    asi dos operaciones al mismo tiempo no se pisan
    """
    if cantidad == 0:
        raise ValueError("La cantidad del movimiento no puede ser cero")

    bloqueado = Producto.objects.select_for_update().get(pk=producto.pk)
    if bloqueado.existencia + cantidad < 0:
        raise ExistenciaInsuficiente(bloqueado, bloqueado.existencia, -cantidad)

    Producto.objects.filter(pk=bloqueado.pk).update(existencia=F("existencia") + cantidad)
    bloqueado.refresh_from_db(fields=["existencia"])
    producto.existencia = bloqueado.existencia

    return MovimientoInventario.objects.create(
        producto=bloqueado,
        tipo=tipo,
        cantidad=cantidad,
        existencia_resultante=bloqueado.existencia,
        motivo=motivo,
        usuario=usuario,
        venta=venta,
    )
