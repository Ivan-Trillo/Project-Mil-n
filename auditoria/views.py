"""
Three Dots: consulta de la bitacora de auditoria sección 3.1.6 de la ERS

Solo el administrador sabe que existe, a cualquier otro usuario se le responde
404, como si la página no existiera (RF-AUD-05) la pantalla es de solo lectura,
los registros nunca se editan ni se borran (RF-AUD-04)
"""
import csv
from datetime import date, timedelta

from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from core.templatetags.formato import fecha_hora
from cuentas import roles
from cuentas.models import Usuario
from cuentas.permisos import rol_requerido

from .models import RegistroAuditoria

POR_PAGINA = 50

PERIODOS = [
    ("hoy", "Hoy"),
    ("semana", "7 días"),
    ("mes", "30 días"),
    ("todo", "Todo"),
]


def _fecha(texto):
    try:
        return date.fromisoformat(texto)
    except (TypeError, ValueError):
        return None


def _filtrar(request):
    #aplica los filtros de la pantalla lo usan la lista y lo exporta
    registros = RegistroAuditoria.objects.select_related("usuario")
    hoy = timezone.localdate()

    periodo = request.GET.get("periodo", "semana")
    desde = _fecha(request.GET.get("desde"))
    hasta = _fecha(request.GET.get("hasta"))
    if desde or hasta:
        periodo = "rango"
    elif periodo not in dict(PERIODOS):
        periodo = "semana"
    #las fechas escritas a mano se muestran en los campos, las de un periodo no
    desde_campo, hasta_campo = desde, hasta
    if periodo == "hoy":
        desde, hasta = hoy, hoy
    elif periodo == "semana":
        desde, hasta = hoy - timedelta(days=6), hoy
    elif periodo == "mes":
        desde, hasta = hoy - timedelta(days=29), hoy
    if desde:
        registros = registros.filter(fecha__date__gte=desde)
    if hasta:
        registros = registros.filter(fecha__date__lte=hasta)

    categoria = request.GET.get("categoria", "")
    if categoria == "alertas":
        registros = registros.filter(accion__in=RegistroAuditoria.ALERTAS)
    elif RegistroAuditoria.acciones_de(categoria):
        registros = registros.filter(accion__in=RegistroAuditoria.acciones_de(categoria))
    else:
        categoria = ""

    accion = request.GET.get("accion", "")
    if accion in dict(RegistroAuditoria.ACCIONES):
        registros = registros.filter(accion=accion)
    else:
        accion = ""

    usuario_id = request.GET.get("usuario", "")
    if usuario_id.isdigit():
        registros = registros.filter(usuario_id=usuario_id)

    q = request.GET.get("q", "").strip()
    if q:
        busqueda = (
            Q(elemento__icontains=q) | Q(usuario_texto__icontains=q)
            | Q(valor_anterior__icontains=q) | Q(valor_nuevo__icontains=q)
        )
        if q[0].isdigit():
            busqueda |= Q(ip__startswith=q)
        registros = registros.filter(busqueda)

    filtros = {
        "periodo": periodo, "desde": desde_campo, "hasta": hasta_campo,
        "categoria": categoria, "accion": accion, "usuario_id": usuario_id, "q": q,
    }
    return registros.order_by("-fecha", "-pk"), filtros


@rol_requerido(roles.ADMINISTRADOR, ocultar=True)
@require_GET
def bitacora(request):
    """RF-AUD-03: consulta de la bitácora con filtros por fecha, tipo de evento y usuario."""
    registros, filtros = _filtrar(request)
    hoy = timezone.localdate()
    hace_7 = hoy - timedelta(days=6)
    todos = RegistroAuditoria.objects

    pagina = Paginator(registros, POR_PAGINA).get_page(request.GET.get("pagina"))
    parametros = request.GET.copy()
    parametros.pop("pagina", None)

    return render(request, "auditoria/bitacora.html", {
        **filtros,
        "pagina": pagina,
        "parametros": parametros.urlencode(),
        "periodos": PERIODOS,
        "accion_texto": dict(RegistroAuditoria.ACCIONES).get(filtros["accion"], ""),
        "categorias": [(c[0], c[1]) for c in RegistroAuditoria.CATEGORIAS],
        "usuarios": Usuario.objects.filter(registros_auditoria__isnull=False).distinct().order_by("username"),
        "hoy": hoy,
        # Resumen rápido para el Administrador
        "eventos_hoy": todos.filter(fecha__date=hoy).count(),
        "fallidos_hoy": todos.filter(fecha__date=hoy, accion=RegistroAuditoria.LOGIN_FALLIDO).count(),
        "cancelaciones_7": todos.filter(fecha__date__gte=hace_7, accion=RegistroAuditoria.VENTA_CANCELACION).count(),
        "precios_7": todos.filter(fecha__date__gte=hace_7, accion=RegistroAuditoria.CAMBIO_PRECIO).count(),
    })


@rol_requerido(roles.ADMINISTRADOR, ocultar=True)
@require_GET
def exportar(request):
    """Descarga en CSV los registros con los mismos filtros de la pantalla."""
    registros, _ = _filtrar(request)
    respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = f'attachment; filename="bitacora-{timezone.localdate():%Y%m%d}.csv"'
    respuesta.write("﻿")  # BOM para que Excel respete los acentos
    escritor = csv.writer(respuesta)
    escritor.writerow(["Fecha y hora", "Usuario", "Acción", "Elemento", "Valor anterior", "Valor nuevo", "IP"])
    for r in registros.iterator():
        escritor.writerow([
            fecha_hora(r.fecha),
            r.usuario.username if r.usuario else r.usuario_texto,
            r.get_accion_display(),
            r.elemento,
            r.valor_anterior,
            r.valor_nuevo,
            r.ip or "",
        ])
    return respuesta
