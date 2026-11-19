"""
consultas del panel de control (Dashboard, seccion 3.1.4 de la ERS

todo se calcula con consultas agregadas de PostgreSQL (Sum y Count), asi no se
traen las ventas una por una a Python, solo cuentan las ventas PAGADAS, las
canceladas y los tickets pendientes no suman :p
"""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate

from productos.models import Producto
from ventas.models import DetalleVenta, Venta

CERO = Decimal("0.00")


def ventas_pagadas():
    return Venta.objects.filter(estado=Venta.PAGADA)


def _en_rango(consulta, desde, hasta, campo="fecha_cobro"):
    return consulta.filter(**{f"{campo}__date__gte": desde, f"{campo}__date__lte": hasta})


def resumen_dia(dia):
    """Total vendido, número de ventas, ticket promedio y piezas de un día"""
    ventas = ventas_pagadas().filter(fecha_cobro__date=dia)
    datos = ventas.aggregate(num_ventas=Count("pk"), total=Sum("total"))
    total = datos["total"] or CERO
    num = datos["num_ventas"]
    piezas = DetalleVenta.objects.filter(venta__in=ventas).aggregate(p=Sum("cantidad"))["p"] or 0
    return {
        "total": total,
        "num_ventas": num,
        "promedio": (total / num).quantize(Decimal("0.01")) if num else CERO,
        "piezas": piezas,
    }


def variacion(actual, anterior):
    """
    Cambio contra el día anterior, por ejemplo {"porcentaje": 25, "direccion": "baja"}.
    Devuelve None si ayer no hubo ventas, porque no hay contra qué comparar.
    """
    if not anterior:
        return None
    cambio = round((Decimal(actual) - Decimal(anterior)) * 100 / Decimal(anterior))
    if cambio > 0:
        direccion = "sube"
    elif cambio < 0:
        direccion = "baja"
    else:
        direccion = "igual"
    return {"porcentaje": abs(cambio), "direccion": direccion}


def ventas_por_dia(desde, hasta):

    por_dia = {
        fila["dia"]: fila
        for fila in _en_rango(ventas_pagadas(), desde, hasta)
        .annotate(dia=TruncDate("fecha_cobro"))
        .values("dia")
        .annotate(total=Sum("total"), num_ventas=Count("pk"))
    }
    dias = []
    dia = desde
    while dia <= hasta:
        fila = por_dia.get(dia, {})
        dias.append({"dia": dia, "total": fila.get("total") or CERO, "num_ventas": fila.get("num_ventas", 0)})
        dia += timedelta(days=1)
    maximo = max((d["total"] for d in dias), default=CERO)
    for d in dias:
        #un dia con ventas siempre se ve aunque sea poco (mínimo 2 %)
        d["altura"] = max(2, round(d["total"] * 100 / maximo)) if d["total"] and maximo else 0
        d["es_maximo"] = bool(maximo) and d["total"] == maximo
    return dias


def mas_vendidos(desde, hasta, limite=5):
    #Productos con más piezas vendidas en el rango
    return list(
        DetalleVenta.objects.filter(venta__estado=Venta.PAGADA)
        .filter(venta__fecha_cobro__date__gte=desde, venta__fecha_cobro__date__lte=hasta)
        .values("producto_id", "producto__nombre")
        .annotate(piezas=Sum("cantidad"), importe=Sum("subtotal"))
        .order_by("-piezas", "producto__nombre")[:limite]
    )


def ventas_por_cajero(dia):
    return list(
        ventas_pagadas().filter(fecha_cobro__date=dia)
        .values("usuario_id", "usuario__username", "usuario__first_name", "usuario__last_name")
        .annotate(total=Sum("total"), num_ventas=Count("pk"))
        .order_by("-total")
    )


def ultimas_ventas(limite=5):
    return Venta.objects.exclude(estado=Venta.PENDIENTE).select_related("usuario").order_by("-fecha_cobro", "-pk")[:limite]


def existencia_baja(limite=8):
    #RF-DAS-03: productos activos con existencia igual o menor a su minimo
    productos = Producto.con_existencia_baja()
    return productos.order_by("existencia", "nombre")[:limite], productos.count()
