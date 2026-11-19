from datetime import timedelta

from django.shortcuts import render
from django.utils import timezone

from cuentas import roles
from cuentas.permisos import rol_requerido

from . import servicios

PERIODOS = [
    ("7", "7 días"),
    ("30", "30 días"),
    ("mes", "Este mes"),
]


def _rango(periodo, hoy):
    if periodo == "30":
        return hoy - timedelta(days=29), hoy
    if periodo == "mes":
        return hoy.replace(day=1), hoy
    return hoy - timedelta(days=6), hoy


@rol_requerido(*roles.GESTION)
def inicio(request):
    """Panel de control con las cifras del día, la gráfica de ventas y los avisos de inventario."""
    hoy = timezone.localdate()
    ayer = hoy - timedelta(days=1)
    periodo = request.GET.get("periodo", "7")
    if periodo not in dict(PERIODOS):
        periodo = "7"
    desde, hasta = _rango(periodo, hoy)

    resumen_hoy = servicios.resumen_dia(hoy)
    resumen_ayer = servicios.resumen_dia(ayer)
    dias = servicios.ventas_por_dia(desde, hasta)
    bajos, total_bajos = servicios.existencia_baja()

    return render(request, "panel/inicio.html", {
        "hoy": hoy,
        "resumen": resumen_hoy,
        "cambio_total": servicios.variacion(resumen_hoy["total"], resumen_ayer["total"]),
        "cambio_ventas": servicios.variacion(resumen_hoy["num_ventas"], resumen_ayer["num_ventas"]),
        "periodo": periodo,
        "periodos": PERIODOS,
        "dias": dias,
        "total_periodo": sum(d["total"] for d in dias),
        "ventas_periodo": sum(d["num_ventas"] for d in dias),
        "mas_vendidos": servicios.mas_vendidos(desde, hasta),
        "por_cajero": servicios.ventas_por_cajero(hoy),
        "ultimas": servicios.ultimas_ventas(),
        "bajos": bajos,
        "total_bajos": total_bajos,
    })
