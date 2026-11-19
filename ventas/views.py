import json
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET, require_POST

from auditoria.models import RegistroAuditoria
from auditoria.servicios import registrar
from configuracion.models import ConfiguracionNegocio
from cuentas import roles
from cuentas.models import Usuario
from cuentas.permisos import rol_requerido
from productos.models import Categoria, Producto

from . import servicios
from .forms import CancelarVentaForm
from .models import Venta
from .servicios import ErrorCaja

LIMITE_PRODUCTOS = 60


# ---------------------------------------------------------------- Pantalla de caja

@rol_requerido(*roles.TODOS)
def caja(request):
    """RNF-INT-03: pantalla principal de venta."""
    estado = servicios.estado_caja(request.user)
    return render(request, "ventas/caja.html", {
        "estado_inicial": estado,
        "categorias": Categoria.objects.filter(activa=True, productos__activo=True).distinct(),
    })


# ---------------------------------------------------------------- API de la caja (JSON)

def _datos(request):
    try:
        return json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return {}


def _respuesta(request, venta_id=None, **extra):
    return JsonResponse({"ok": True, "estado": servicios.estado_caja(request.user, venta_id), **extra})


def _error(mensaje, status=400, **extra):
    return JsonResponse({"ok": False, "error": mensaje, **extra}, status=status)


def _decimal(valor):
    try:
        return Decimal(str(valor).replace(",", "").replace("$", "").strip())
    except (InvalidOperation, ValueError):
        raise ErrorCaja("Escribe un importe válido, por ejemplo 200 o 150.50.")


def _entero(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        raise ErrorCaja("Escribe una cantidad válida.")


def api(funcion):
    """Convierte los ErrorCaja en una respuesta JSON con el mensaje para el cajero."""
    def envoltura(request, *args, **kwargs):
        try:
            return funcion(request, *args, **kwargs)
        except ErrorCaja as error:
            return _error(str(error))
    envoltura.__name__ = funcion.__name__
    return envoltura


@require_GET
@rol_requerido(*roles.TODOS)
@api
def api_estado(request):
    activo = request.GET.get("ticket")
    return _respuesta(request, int(activo) if activo and activo.isdigit() else None)


@require_POST
@rol_requerido(*roles.TODOS)
@api
def api_nuevo_ticket(request):
    venta = servicios.nuevo_ticket(request.user)
    return _respuesta(request, venta.pk)


@require_POST
@rol_requerido(*roles.TODOS)
@api
def api_descartar(request, pk):
    servicios.descartar_ticket(servicios.obtener_ticket(request.user, pk))
    return _respuesta(request)


@require_POST
@rol_requerido(*roles.TODOS)
@api
def api_agregar(request, pk):
    """
    Agrega por código de barras ({"codigo": "750..."}) o por producto ({"producto_id": 5})
    También acepta "6*750..." para agregar varias piezas de una vez (Agregar varios)
    """
    venta = servicios.obtener_ticket(request.user, pk)
    datos = _datos(request)
    cantidad = _entero(datos.get("cantidad", 1))

    if datos.get("producto_id"):
        producto = Producto.objects.filter(pk=datos["producto_id"], activo=True).first()
    else:
        codigo = str(datos.get("codigo", "")).strip()
        if "*" in codigo:
            prefijo, codigo = codigo.split("*", 1)
            cantidad = _entero(prefijo)
        producto = servicios.buscar_por_codigo(codigo)
        if producto is None:
            # RF-VEN-02
            return _error("Producto no encontrado", codigo="no_encontrado")

    if producto is None:
        return _error("Producto no encontrado", codigo="no_encontrado")
    detalle = servicios.agregar_producto(venta, producto, cantidad)
    return _respuesta(request, venta.pk, linea_id=detalle.pk)


@require_POST
@rol_requerido(*roles.TODOS)
@api
def api_cantidad(request, pk, detalle_id):
    venta = servicios.obtener_ticket(request.user, pk)
    servicios.cambiar_cantidad(venta, detalle_id, _entero(_datos(request).get("cantidad")))
    return _respuesta(request, venta.pk)


@require_POST
@rol_requerido(*roles.TODOS)
@api
def api_quitar(request, pk, detalle_id):
    venta = servicios.obtener_ticket(request.user, pk)
    servicios.quitar_producto(venta, detalle_id)
    return _respuesta(request, venta.pk)


@require_POST
@rol_requerido(*roles.TODOS)
@api
def api_descuento(request, pk):
    venta = servicios.obtener_ticket(request.user, pk)
    servicios.aplicar_descuento(venta, _decimal(_datos(request).get("monto", 0)))
    return _respuesta(request, venta.pk)


@require_POST
@rol_requerido(*roles.TODOS)
@api
def api_cobrar(request, pk):
    venta = servicios.obtener_ticket(request.user, pk)
    venta = servicios.cobrar(venta, _decimal(_datos(request).get("monto_recibido")))
    # Después de cobrar se abre un ticket nuevo si ya no queda ninguno
    return _respuesta(
        request,
        venta={
            "id": venta.pk,
            "folio": venta.folio_texto,
            "total": str(venta.total),
            "recibido": str(venta.monto_recibido),
            "cambio": str(venta.cambio),
        },
    )


@require_GET
@rol_requerido(*roles.TODOS)
def api_productos(request):
    """Cuadrícula de productos (por categoría) y búsqueda por nombre (RF-VEN-03)."""
    productos = Producto.objects.filter(activo=True).select_related("categoria")
    q = request.GET.get("q", "").strip()
    categoria = request.GET.get("categoria", "")
    if q:
        if len(q) < 3:
            return JsonResponse({"productos": []})
        productos = productos.filter(Q(nombre__icontains=q) | Q(codigo_barras=q) | Q(sku__iexact=q))
    elif categoria.isdigit():
        productos = productos.filter(categoria_id=categoria)
    datos = [{
        "id": p.pk,
        "nombre": p.nombre,
        "precio": str(p.precio_venta),
        "existencia": p.existencia,
        "imagen": p.imagen.url if p.imagen else "",
        "categoria": p.categoria.nombre if p.categoria else "",
    } for p in productos.order_by("nombre")[:LIMITE_PRODUCTOS]]
    return JsonResponse({"productos": datos})


# ---------------------------------------------------------------- Ticket impreso

@xframe_options_sameorigin  # la caja lo carga en un iframe para imprimirlo sin salir de la pantalla
@rol_requerido(*roles.TODOS)
def ticket_impreso(request, pk):
    """
    RF-VEN-14 y RF-VEN-16: ticket para imprimir (y reimprimir) en papel de 58 u 80 mm.
    El cajero solo puede ver los tickets de sus ventas; el Encargado y el Administrador, todos.
    """
    ventas = Venta.objects.exclude(estado=Venta.PENDIENTE).select_related("usuario")
    if not request.user.tiene_rol(*roles.GESTION):
        ventas = ventas.filter(usuario=request.user)
    venta = get_object_or_404(ventas, pk=pk)
    ancho = request.GET.get("ancho", "80")
    return render(request, "ventas/ticket_impreso.html", {
        "venta": venta,
        "detalles": venta.detalles.select_related("producto"),
        "negocio": ConfiguracionNegocio.obtener(),
        "ancho": "58" if ancho == "58" else "80",
        "imprimir": request.GET.get("imprimir") == "1",
        # RF-VEN-16: la reimpresión lleva la leyenda de copia para no confundirla con el original
        "copia": request.GET.get("copia") == "1",
        "ahora": timezone.now(),
    })


# ---------------------------------------------------------------- Registro (historial de ventas)

POR_PAGINA_REGISTRO = 30

PERIODOS = [
    ("hoy", "Hoy"),
    ("ayer", "Ayer"),
    ("semana", "Últimos 7 días"),
    ("mes", "Este mes"),
    ("todo", "Todo"),
]


def _fecha(texto):
    try:
        return date.fromisoformat(texto)
    except (TypeError, ValueError):
        return None


def _rango(periodo, desde, hasta):
    """Devuelve (desde, hasta) como fechas locales, o (None, None) para no filtrar."""
    hoy = timezone.localdate()
    if periodo == "rango":
        return desde, hasta
    if periodo == "ayer":
        ayer = hoy - timedelta(days=1)
        return ayer, ayer
    if periodo == "semana":
        return hoy - timedelta(days=6), hoy
    if periodo == "mes":
        return hoy.replace(day=1), hoy
    if periodo == "todo":
        return None, None
    return hoy, hoy


@rol_requerido(*roles.GESTION)
def historial(request):
    """
    Registro: historial de ventas cobradas y canceladas, con filtros por fecha,
    folio, cajero y estado. Los tickets pendientes no aparecen porque todavía no
    son ventas.
    """
    ventas = Venta.objects.exclude(estado=Venta.PENDIENTE).select_related("usuario")

    q = request.GET.get("q", "").strip().lstrip("#")
    periodo = request.GET.get("periodo", "hoy")
    desde = _fecha(request.GET.get("desde"))
    hasta = _fecha(request.GET.get("hasta"))
    if desde or hasta:
        periodo = "rango"
    if periodo not in dict(PERIODOS) and periodo != "rango":
        periodo = "hoy"
    cajero_id = request.GET.get("cajero", "")
    estado = request.GET.get("estado", "")

    if q:
        # Buscar por folio ignora las fechas, así se encuentra un ticket viejo
        ventas = ventas.filter(folio=int(q)) if q.isdigit() and len(q) <= 9 else ventas.none()
    else:
        inicio, fin = _rango(periodo, desde, hasta)
        if inicio:
            ventas = ventas.filter(fecha_cobro__date__gte=inicio)
        if fin:
            ventas = ventas.filter(fecha_cobro__date__lte=fin)
    if cajero_id.isdigit():
        ventas = ventas.filter(usuario_id=cajero_id)
    if estado == "pagadas":
        ventas = ventas.filter(estado=Venta.PAGADA)
    elif estado == "canceladas":
        ventas = ventas.filter(estado=Venta.CANCELADA)

    # Resumen del periodo: las canceladas no cuentan como vendido
    resumen = ventas.aggregate(
        num_ventas=Count("pk", filter=Q(estado=Venta.PAGADA)),
        total=Sum("total", filter=Q(estado=Venta.PAGADA)),
        num_canceladas=Count("pk", filter=Q(estado=Venta.CANCELADA)),
    )
    resumen["total"] = resumen["total"] or Decimal("0.00")
    resumen["promedio"] = (
        servicios.redondear(resumen["total"] / resumen["num_ventas"]) if resumen["num_ventas"] else Decimal("0.00")
    )

    lista = ventas.annotate(piezas=Sum("detalles__cantidad")).order_by("-fecha_cobro", "-pk")
    pagina = Paginator(lista, POR_PAGINA_REGISTRO).get_page(request.GET.get("pagina"))
    filtros = request.GET.copy()
    filtros.pop("pagina", None)

    return render(request, "ventas/historial.html", {
        "pagina": pagina,
        "resumen": resumen,
        "q": q,
        "periodo": periodo,
        "periodos": PERIODOS,
        "desde": desde,
        "hasta": hasta,
        "cajero_id": cajero_id,
        "estado": estado,
        "cajeros": Usuario.objects.filter(ventas__estado__in=[Venta.PAGADA, Venta.CANCELADA]).distinct().order_by("username"),
        "filtros": filtros.urlencode(),
        "hoy": timezone.localdate(),
    })


@rol_requerido(*roles.GESTION)
def venta_detalle(request, pk):
    """Detalle de una venta con sus productos, pagos y, si aplica, los datos de la cancelación."""
    venta = get_object_or_404(
        Venta.objects.exclude(estado=Venta.PENDIENTE).select_related("usuario", "cancelada_por"), pk=pk
    )
    detalles = list(venta.detalles.select_related("producto", "producto__categoria"))
    return render(request, "ventas/venta_detalle.html", {
        "venta": venta,
        "detalles": detalles,
        "piezas": sum(d.cantidad for d in detalles),
        "form_cancelar": CancelarVentaForm(),
        "negocio": ConfiguracionNegocio.obtener(),
    })


@require_POST
@rol_requerido(*roles.GESTION)
def venta_cancelar(request, pk):
    """
    RF-VEN-17: cancela la venta, regresa el inventario y lo anota en la bitácora.
    Todo pasa en una sola transacción, si algo falla no queda nada a medias.
    """
    venta = get_object_or_404(Venta.objects.exclude(estado=Venta.PENDIENTE), pk=pk)
    form = CancelarVentaForm(request.POST)
    if not form.is_valid():
        for errores in form.errors.values():
            for error in errores:
                messages.error(request, error)
        return redirect("ventas:detalle", pk=venta.pk)

    try:
        with transaction.atomic():
            venta = servicios.cancelar_venta(venta, request.user, form.cleaned_data["motivo"])
            registrar(
                request, RegistroAuditoria.VENTA_CANCELACION, elemento=venta,
                anterior=f"Pagada, total {venta.total}",
                nuevo=f"Cancelada: {venta.motivo_cancelacion}",
            )
    except ErrorCaja as error:
        messages.error(request, str(error))
    else:
        messages.success(
            request,
            f"Se canceló la venta {venta.folio_texto}. Los productos regresaron al inventario.",
        )
    return redirect("ventas:detalle", pk=venta.pk)
