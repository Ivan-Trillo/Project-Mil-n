"""
Filtros para mostrar datos con el formato de la ERS

Se cargan automaticamente en todas las plantillas (ver TEMPLATES en settings),
así que no hace falta {% load formato %}

    {{ producto.precio_venta|pesos }}   ->  $1,234.56   (RNF-INT-04)
    {{ venta.fecha_cobro|fecha_hora }}  ->  18/11/2026 17:20   (RNF-INT-05)
    {{ venta.fecha_cobro|fecha }}       ->  18/11/2026
"""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django import template
from django.utils import timezone

register = template.Library()


@register.filter
def pesos(valor):
    #Formatea un importe en pesos mexicanos por ejemplo $1,234.56
    if valor in (None, ""):
        return ""
    try:
        numero = Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return valor
    signo = "-" if numero < 0 else ""
    return f"{signo}${abs(numero):,.2f}"


def _local(valor):
    if valor is None or valor == "":
        return None
    if timezone.is_aware(valor):
        return timezone.localtime(valor)
    return valor


@register.filter
def fecha(valor):
    #DD/MM/AAAA en la zona horaria del negocio
    valor = _local(valor)
    return valor.strftime("%d/%m/%Y") if valor else ""


@register.filter
def fecha_hora(valor):
    #DD/MM/AAAA HH:MM (24 horas) en la zona horaria del negocio
    valor = _local(valor)
    return valor.strftime("%d/%m/%Y %H:%M") if valor else ""
