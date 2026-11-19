from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from configuracion.models import ConfiguracionNegocio
from productos.models import MovimientoInventario, Producto
from productos.servicios import ExistenciaInsuficiente, registrar_movimiento

from .models import DetalleVenta, SecuenciaFolio, Venta

CENTAVO = Decimal("0.01")
MAX_TICKETS_ABIERTOS = 10  # RF-VEN-09 pide al menos 5


class ErrorCaja(Exception):
    """Error que se le muestra tal cual al cajero"""


def redondear(valor):
    return Decimal(valor).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def tasa_impuesto():
    config = ConfiguracionNegocio.obtener()
    return config.tasa_impuesto if config else Decimal("16.00")


# ---------------------------------------------------------------- Tickets

def tickets_abiertos(usuario):
    return Venta.objects.filter(usuario=usuario, estado=Venta.PENDIENTE).order_by("creada", "pk")


def nuevo_ticket(usuario):
    if tickets_abiertos(usuario).count() >= MAX_TICKETS_ABIERTOS:
        raise ErrorCaja(f"Ya tienes {MAX_TICKETS_ABIERTOS} tickets abiertos. Cobra o descarta alguno antes de abrir otro")
    return Venta.objects.create(usuario=usuario)


def obtener_ticket(usuario, pk):
    #Un cajero solo puede tocar sus propios tickets pendientes
    venta = Venta.objects.filter(pk=pk, usuario=usuario, estado=Venta.PENDIENTE).first()
    if venta is None:
        raise ErrorCaja("Ese ticket ya no está abierto.")
    return venta


def descartar_ticket(venta):
    #Un ticket pendiente todavia no es una venta, asi que si se puede eliminar
    if venta.estado != Venta.PENDIENTE:
        raise ErrorCaja("Solo se pueden descartar tickets que no se han cobrado")
    venta.delete()


# ---------------------------------------------------------------- Totales

def recalcular(venta):
    """
    RF-VEN-08: subtotal, descuento, total e IVA incluido, redondeados a 2 decimales
    Los precios ya incluyen IVA (SUP-03), así que el IVA se "saca" del total
    """
    subtotal = sum((d.subtotal for d in venta.detalles.all()), Decimal("0"))
    venta.subtotal = redondear(subtotal)
    if venta.descuento > venta.subtotal:
        venta.descuento = venta.subtotal
    venta.total = redondear(venta.subtotal - venta.descuento)
    tasa = tasa_impuesto()
    venta.impuesto = redondear(venta.total * tasa / (Decimal("100") + tasa))
    venta.save(update_fields=["subtotal", "descuento", "total", "impuesto"])
    return venta


# ---------------------------------------------------------------- Productos del ticket

def buscar_por_codigo(codigo):
    #RF-VEN-01 y RF-VEN-02: busca un producto activo por codigo de barras o SKU
    codigo = (codigo or "").strip()
    if not codigo:
        return None
    return (
        Producto.objects.filter(activo=True, codigo_barras=codigo).first()
        or Producto.objects.filter(activo=True, sku__iexact=codigo).first()
    )


@transaction.atomic
def agregar_producto(venta, producto, cantidad=1):
    """
    RF-VEN-01 y RF-VEN-04: agrega el producto o suma a su cantidad si ya estaba
    RF-VEN-07: no deja pasar de la existencia disponible
    """
    if not producto.activo:
        raise ErrorCaja(f"«{producto}» está dado de baja y no se puede vender")
    if cantidad < 1:
        raise ErrorCaja("La cantidad debe ser al menos 1")

    detalle = venta.detalles.filter(producto=producto).first()
    nueva_cantidad = (detalle.cantidad if detalle else 0) + cantidad
    validar_existencia(producto, nueva_cantidad)

    if detalle is None:
        # RNF-BD-04: el precio se copia en el momento en que se agrega
        detalle = DetalleVenta(venta=venta, producto=producto, cantidad=0, precio_unitario=producto.precio_venta)
    detalle.cantidad = nueva_cantidad
    detalle.calcular_subtotal()
    detalle.save()
    recalcular(venta)
    return detalle


def validar_existencia(producto, cantidad):
    producto.refresh_from_db(fields=["existencia"])
    if cantidad > producto.existencia:
        if producto.existencia <= 0:
            raise ErrorCaja(f"«{producto}» no tiene existencia.")
        raise ErrorCaja(f"Solo hay {producto.existencia} de «{producto}» en existencia.")


@transaction.atomic
def cambiar_cantidad(venta, detalle_id, cantidad):
    """RF-VEN-05 (Cambiar). Con cantidad 0 se quita la línea."""
    detalle = venta.detalles.select_related("producto").filter(pk=detalle_id).first()
    if detalle is None:
        raise ErrorCaja("Ese producto ya no está en el ticket.")
    if cantidad <= 0:
        detalle.delete()
    else:
        validar_existencia(detalle.producto, cantidad)
        detalle.cantidad = cantidad
        detalle.calcular_subtotal()
        detalle.save()
    recalcular(venta)


@transaction.atomic
def quitar_producto(venta, detalle_id):
    """RF-VEN-06 (Borrar)."""
    venta.detalles.filter(pk=detalle_id).delete()
    recalcular(venta)


@transaction.atomic
def aplicar_descuento(venta, monto):
    monto = redondear(monto)
    if monto < 0:
        raise ErrorCaja("El descuento no puede ser negativo.")
    recalcular(venta)  # asegura el subtotal actualizado
    if monto > venta.subtotal:
        raise ErrorCaja("El descuento no puede ser mayor que el subtotal.")
    venta.descuento = monto
    venta.save(update_fields=["descuento"])
    recalcular(venta)


# ---------------------------------------------------------------- Cobro

@transaction.atomic
def cobrar(venta, monto_recibido):
    venta = Venta.objects.select_for_update().get(pk=venta.pk)
    if venta.estado != Venta.PENDIENTE:
        raise ErrorCaja("Este ticket ya fue cobrado.")
    detalles = list(venta.detalles.select_related("producto"))
    if not detalles:
        raise ErrorCaja("El ticket está vacío.")

    recalcular(venta)
    monto_recibido = redondear(monto_recibido)
    if monto_recibido < venta.total:
        raise ErrorCaja(f"El monto recibido es menor que el total a pagar")

    try:
        for detalle in detalles:
            registrar_movimiento(
                detalle.producto,
                MovimientoInventario.VENTA,
                -detalle.cantidad,
                venta.usuario,
                venta=venta,
            )
    except ExistenciaInsuficiente as error:
        raise ErrorCaja(
            f"Ya no hay suficiente «{error.producto}»: quedan {error.disponible}. Ajusta la cantidad e intenta de nuevo"
        ) from error

    venta.folio = SecuenciaFolio.siguiente()
    venta.estado = Venta.PAGADA
    venta.fecha_cobro = timezone.now()
    venta.monto_recibido = monto_recibido
    venta.cambio = redondear(monto_recibido - venta.total)
    venta.save()
    return venta


# ---------------------------------------------------------------- Representación para la pantalla

def ticket_a_dict(venta, numero=None):
    lineas = []
    for d in venta.detalles.select_related("producto", "producto__categoria"):
        lineas.append({
            "id": d.pk,
            "producto_id": d.producto_id,
            "nombre": d.producto.nombre,
            "categoria": d.producto.categoria.nombre if d.producto.categoria else "",
            "imagen": d.producto.imagen.url if d.producto.imagen else "",
            "cantidad": d.cantidad,
            "precio": str(d.precio_unitario),
            "subtotal": str(d.subtotal),
            "existencia": d.producto.existencia,
        })
    return {
        "id": venta.pk,
        "numero": numero,
        "lineas": lineas,
        "piezas": sum(l["cantidad"] for l in lineas),
        "subtotal": str(venta.subtotal),
        "descuento": str(venta.descuento),
        "total": str(venta.total),
        "impuesto": str(venta.impuesto),
    }


def estado_caja(usuario, activo_id=None):
    """Todos los tickets abiertos del usuario y el detalle del ticket activo."""
    tickets = list(tickets_abiertos(usuario))
    if not tickets:
        tickets = [nuevo_ticket(usuario)]
    ids = [t.pk for t in tickets]
    activo = next((t for t in tickets if t.pk == activo_id), tickets[-1])
    return {
        "tickets": [{"id": t.pk, "numero": i + 1} for i, t in enumerate(tickets)],
        "activo": ticket_a_dict(activo, numero=ids.index(activo.pk) + 1),
        "max_tickets": MAX_TICKETS_ABIERTOS,
    }


# ---------------------------------------------------------------- Cancelacion (RF-VEN-17)

@transaction.atomic
def cancelar_venta(venta, usuario, motivo):
    motivo = (motivo or "").strip()
    if not motivo:
        raise ErrorCaja("Escribe el motivo de la cancelacion")

    venta = Venta.objects.select_for_update().get(pk=venta.pk)
    if venta.estado == Venta.CANCELADA:
        raise ErrorCaja("Esta venta ya estaba cancelada.")
    if venta.estado != Venta.PAGADA:
        raise ErrorCaja("Solo se pueden cancelar ventas cobradas.")

    for detalle in venta.detalles.select_related("producto"):
        registrar_movimiento(
            detalle.producto,
            MovimientoInventario.CANCELACION,
            detalle.cantidad,
            usuario,
            motivo=f"Cancelación de la venta {venta.folio_texto}",
            venta=venta,
        )

    venta.estado = Venta.CANCELADA
    venta.motivo_cancelacion = motivo[:200]
    venta.cancelada_por = usuario
    venta.fecha_cancelacion = timezone.now()
    venta.save(update_fields=["estado", "motivo_cancelacion", "cancelada_por", "fecha_cancelacion"])
    return venta
