from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from auditoria.models import RegistroAuditoria
from auditoria.servicios import registrar
from cuentas import roles
from cuentas.permisos import rol_requerido

from .forms import CategoriaForm, MovimientoForm, ProductoForm, ProveedorForm
from .models import Categoria, MovimientoInventario, Producto, Proveedor
from .servicios import ExistenciaInsuficiente, registrar_movimiento

POR_PAGINA = 24


# ---------------------------------------------------------------- Catalogo

@rol_requerido(*roles.TODOS)
def catalogo(request):
    #RF-PRO-04 y RF-PRO-10: consulta, busqueda, filtros y marca de existencia baja
    productos = Producto.objects.select_related("categoria")
    q = request.GET.get("q", "").strip()
    categoria_id = request.GET.get("categoria", "")
    estado = request.GET.get("estado", "activos")
    puede_gestionar = request.user.tiene_rol(*roles.GESTION)

    if q:
        productos = productos.filter(
            Q(nombre__icontains=q) | Q(codigo_barras__iexact=q) | Q(sku__iexact=q)
        )
    if categoria_id.isdigit():
        productos = productos.filter(categoria_id=categoria_id)

    #el cajero solo ve productos activos
    if not puede_gestionar or estado == "activos":
        productos = productos.filter(activo=True)
    elif estado == "inactivos":
        productos = productos.filter(activo=False)
    elif estado == "bajos":
        productos = productos.filter(activo=True, existencia__lte=F("existencia_minima"))

    pagina = Paginator(productos.order_by("nombre"), POR_PAGINA).get_page(request.GET.get("pagina"))
    filtros = request.GET.copy()
    filtros.pop("pagina", None)

    return render(request, "productos/catalogo.html", {
        "pagina": pagina,
        "categorias": Categoria.objects.filter(activa=True),
        "q": q,
        "categoria_id": categoria_id,
        "estado": estado,
        "puede_gestionar": puede_gestionar,
        "total_bajos": Producto.con_existencia_baja().count() if puede_gestionar else 0,
        "filtros": filtros.urlencode(),
    })


@rol_requerido(*roles.GESTION)
def producto_detalle(request, pk):
    #RF-PRO-09: datos del producto e historial de movimientos
    producto = get_object_or_404(Producto.objects.select_related("categoria", "proveedor"), pk=pk)
    movimientos = producto.movimientos.select_related("usuario", "venta")
    pagina = Paginator(movimientos, 30).get_page(request.GET.get("pagina"))
    return render(request, "productos/producto_detalle.html", {
        "producto": producto,
        "pagina": pagina,
        "form_movimiento": MovimientoForm(producto=producto),
    })


# ---------------------------------------------------------------- Alta y edicion

@rol_requerido(*roles.GESTION)
def producto_nuevo(request):
    # de RF-PRO-01 a RF-PRO-03
    form = ProductoForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            existencia_inicial = form.cleaned_data.get("existencia") or 0
            producto = form.save(commit=False)
            producto.existencia = 0
            producto.save()
            if existencia_inicial:
                registrar_movimiento(
                    producto, MovimientoInventario.ENTRADA, existencia_inicial,
                    request.user, motivo="Existencia inicial",
                )
            registrar(
                request, RegistroAuditoria.PRODUCTO_ALTA, elemento=producto,
                nuevo=f"SKU {producto.sku}, precio {producto.precio_venta}, existencia {existencia_inicial}",
            )
        messages.success(request, f"Se registró el producto «{producto}».")
        if "otro" in request.POST:
            return redirect("productos:nuevo")
        return redirect("productos:catalogo")
    return render(request, "productos/producto_form.html", {"form": form})


@rol_requerido(*roles.GESTION)
def producto_editar(request, pk):
    #RF-PRO-05 los cambios no afectan las ventas pasadas porque cada detalle guarda su precio
    producto = get_object_or_404(Producto, pk=pk)
    precio_anterior = producto.precio_venta
    form = ProductoForm(request.POST or None, request.FILES or None, instance=producto)
    if request.method == "POST" and form.is_valid():
        if form.has_changed():
            antes = {campo: form.initial.get(campo) for campo in form.changed_data}
            producto = form.save()
            cambios = [c for c in form.changed_data if c != "precio_venta"]
            if "precio_venta" in form.changed_data:
                registrar(
                    request, RegistroAuditoria.CAMBIO_PRECIO, elemento=producto,
                    anterior=precio_anterior, nuevo=producto.precio_venta,
                )
            if cambios:
                registrar(
                    request, RegistroAuditoria.PRODUCTO_EDICION, elemento=producto,
                    anterior="\n".join(f"{form.fields[c].label}: {antes[c] or ''}" for c in cambios),
                    nuevo="\n".join(f"{form.fields[c].label}: {form.cleaned_data[c] or ''}" for c in cambios),
                )
            messages.success(request, f"Se guardaron los cambios de «{producto}».")
        return redirect("productos:detalle", pk=producto.pk)
    return render(request, "productos/producto_form.html", {"form": form, "producto": producto})


@require_POST
@rol_requerido(*roles.GESTION)
def producto_estado(request, pk):
    """RF-PRO-06: dar de baja (desactivar) o reactivar, nunca borrar."""
    producto = get_object_or_404(Producto, pk=pk)
    producto.activo = not producto.activo
    producto.save(update_fields=["activo", "actualizado"])
    registrar(
        request, RegistroAuditoria.PRODUCTO_BAJA if not producto.activo else RegistroAuditoria.PRODUCTO_EDICION,
        elemento=producto,
        anterior="Activo" if not producto.activo else "Inactivo",
        nuevo="Inactivo" if not producto.activo else "Activo",
    )
    if producto.activo:
        messages.success(request, f"«{producto}» se reactivó y ya aparece en la caja.")
    else:
        messages.success(request, f"«{producto}» se dio de baja. Ya no aparece en la caja, pero se conserva en las ventas anteriores")
    return redirect("productos:detalle", pk=producto.pk)


@require_POST
@rol_requerido(*roles.GESTION)
def producto_movimiento(request, pk):
    """RF-PRO-08: entrada o ajuste de inventario."""
    producto = get_object_or_404(Producto, pk=pk)
    form = MovimientoForm(request.POST, producto=producto)
    if form.is_valid():
        anterior = producto.existencia
        try:
            registrar_movimiento(
                producto, form.cleaned_data["tipo"], form.cleaned_data["cantidad"],
                request.user, motivo=form.cleaned_data["motivo"].strip(),
            )
        except ExistenciaInsuficiente as error:
            messages.error(request, str(error))
        else:
            registrar(
                request, RegistroAuditoria.INVENTARIO_AJUSTE, elemento=producto,
                anterior=f"Existencia {anterior}",
                nuevo=f"Existencia {producto.existencia} ({form.cleaned_data['cantidad']:+d}, {form.cleaned_data['motivo'] or form.cleaned_data['tipo'].lower()})",
            )
            messages.success(request, f"Movimiento registrado. Existencia actual de «{producto}»: {producto.existencia}.")
            return redirect("productos:detalle", pk=producto.pk)
    else:
        for errores in form.errors.values():
            for error in errores:
                messages.error(request, error)
    return redirect("productos:detalle", pk=producto.pk)


# ---------------------------------------------------------------- Categorias (RF-PRO-07)

@rol_requerido(*roles.GESTION)
def categorias(request, pk=None):
    """Lista de categorías con su formulario de alta o edición en la misma pantalla."""
    editando = get_object_or_404(Categoria, pk=pk) if pk else None
    form = CategoriaForm(request.POST or None, instance=editando)
    if request.method == "POST" and form.is_valid():
        categoria = form.save()
        messages.success(request, f"Categoría «{categoria}» guardada.")
        return redirect("productos:categorias")
    return render(request, "productos/categorias.html", {
        "categorias": Categoria.objects.all(),
        "form": form,
        "editando": editando,
    })


@require_POST
@rol_requerido(*roles.GESTION)
def categoria_estado(request, pk):
    categoria = get_object_or_404(Categoria, pk=pk)
    categoria.activa = not categoria.activa
    categoria.save(update_fields=["activa"])
    messages.success(request, f"Categoría «{categoria}» {'activada' if categoria.activa else 'desactivada'}.")
    return redirect("productos:categorias")


# ---------------------------------------------------------------- Proveedores

@rol_requerido(*roles.GESTION)
def proveedores(request):
    lista = Proveedor.objects.all()
    q = request.GET.get("q", "").strip()
    if q:
        lista = lista.filter(Q(nombre__icontains=q) | Q(contacto__icontains=q) | Q(rfc__iexact=q))
    return render(request, "productos/proveedores.html", {"proveedores": lista, "q": q})


@rol_requerido(*roles.GESTION)
def proveedor_form(request, pk=None):
    proveedor = get_object_or_404(Proveedor, pk=pk) if pk else None
    form = ProveedorForm(request.POST or None, instance=proveedor)
    if request.method == "POST" and form.is_valid():
        es_nuevo = proveedor is None
        #se toma de form.initial porque al validar Django ya le puso los datos nuevos al objeto
        antes = {c: form.initial.get(c) for c in form.changed_data} if proveedor else {}
        proveedor = form.save()
        #RF-AUD-01: alta y edicion de proveedores quedan en la bitacora
        if es_nuevo:
            registrar(request, RegistroAuditoria.PROVEEDOR_ALTA, elemento=f"Proveedor {proveedor}",
                      nuevo=f"Contacto: {proveedor.contacto or '-'}, teléfono: {proveedor.telefono or '-'}")
        elif form.changed_data:
            registrar(
                request, RegistroAuditoria.PROVEEDOR_EDICION, elemento=f"Proveedor {proveedor}",
                anterior="\n".join(f"{form.fields[c].label}: {antes[c] or ''}" for c in form.changed_data),
                nuevo="\n".join(f"{form.fields[c].label}: {form.cleaned_data[c] or ''}" for c in form.changed_data),
            )
        messages.success(request, f"Proveedor «{proveedor}» guardado.")
        return redirect("proveedores:lista")
    return render(request, "productos/proveedor_form.html", {"form": form, "proveedor": proveedor})


@require_POST
@rol_requerido(*roles.GESTION)
def proveedor_estado(request, pk):
    proveedor = get_object_or_404(Proveedor, pk=pk)
    proveedor.activo = not proveedor.activo
    proveedor.save(update_fields=["activo"])
    registrar(
        request, RegistroAuditoria.PROVEEDOR_ESTADO, elemento=f"Proveedor {proveedor}",
        anterior="Inactivo" if proveedor.activo else "Activo",
        nuevo="Activo" if proveedor.activo else "Inactivo",
    )
    messages.success(request, f"Proveedor «{proveedor}» {'activado' if proveedor.activo else 'desactivado'}.")
    return redirect("proveedores:lista")
