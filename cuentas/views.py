from django.contrib import messages
from django.contrib.auth.views import PasswordChangeView
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST

from auditoria.models import RegistroAuditoria
from auditoria.servicios import registrar

from . import roles
from .forms import CambiarPasswordForm, EmpleadoForm, EmpleadoNuevoForm, RestablecerPasswordForm
from .models import Usuario
from .permisos import rol_requerido
from .servicios import ErrorEmpleados, asignar_rol, validar_queda_un_administrador


class CambiarPasswordView(PasswordChangeView):
    
    #RF-AUT-06: cada usuario cambia su propia contraseña, tambien es la pantalla a la que se obliga a entrar despues de un
    #restablecimiento hecho por el admin (RF-USR-05).

    form_class = CambiarPasswordForm
    template_name = "cuentas/cambiar_password.html"
    success_url = reverse_lazy("inicio")

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        usuario = self.request.user
        if usuario.debe_cambiar_password:
            usuario.debe_cambiar_password = False
            usuario.save(update_fields=["debe_cambiar_password"])
        messages.success(self.request, "Tu contraseña se cambió correctamente.")
        return respuesta


# ---------------------------------------------------------------- Empleados (sección 3.1.5)
# Solo el Administrador gestiona empleados

@rol_requerido(roles.ADMINISTRADOR)
def empleados(request):
    """Lista de empleados con búsqueda y filtros por rol y estado"""
    lista = Usuario.objects.prefetch_related("groups")
    q = request.GET.get("q", "").strip()
    rol = request.GET.get("rol", "")
    estado = request.GET.get("estado", "activos")
    if q:
        lista = lista.filter(
            Q(username__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(email__icontains=q)
        )
    if rol in roles.TODOS:
        lista = lista.filter(groups__name=rol)
    if estado == "activos":
        lista = lista.filter(is_active=True)
    elif estado == "inactivos":
        lista = lista.filter(is_active=False)
    return render(request, "cuentas/empleados.html", {
        "empleados": lista.order_by("first_name", "last_name", "username").distinct(),
        "q": q,
        "rol": rol,
        "estado": estado,
        "roles": roles.TODOS,
    })


@rol_requerido(roles.ADMINISTRADOR)
def empleado_nuevo(request):
    """RF-USR-01: alta de empleado con rol y contraseña temporal"""
    form = EmpleadoNuevoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            empleado = form.save(commit=False)
            empleado.set_password(form.cleaned_data["password1"])
            empleado.debe_cambiar_password = True
            empleado.save()
            asignar_rol(empleado, form.cleaned_data["rol"])
            registrar(
                request, RegistroAuditoria.USUARIO_ALTA, elemento=f"Usuario {empleado.username}",
                nuevo=f"{empleado}, rol {form.cleaned_data['rol']}",
            )
        messages.success(request, f"Se dio de alta a «{empleado}». Deberá cambiar su contraseña al entrar por primera vez")
        return redirect("cuentas:usuarios")
    return render(request, "cuentas/empleado_nuevo.html", {"form": form})


@rol_requerido(roles.ADMINISTRADOR)
def empleado_editar(request, pk):
    """RF-USR-02 y RF-USR-03: consulta y edición de datos y rol"""
    empleado = get_object_or_404(Usuario, pk=pk)
    rol_anterior = empleado.rol
    form = EmpleadoForm(request.POST or None, instance=empleado)
    if request.method == "POST" and form.is_valid():
        rol_nuevo = form.cleaned_data["rol"]
        try:
            if rol_nuevo != rol_anterior:
                if empleado == request.user:
                    raise ErrorEmpleados("No puedes cambiar tu propio rol.")
                validar_queda_un_administrador(empleado, nuevo_rol=rol_nuevo)
        except ErrorEmpleados as error:
            form.add_error("rol", str(error))
        else:
            cambios = [c for c in form.changed_data if c != "rol"]
            antes = {c: form.initial.get(c) for c in cambios}
            with transaction.atomic():
                empleado = form.save()
                if rol_nuevo != rol_anterior:
                    asignar_rol(empleado, rol_nuevo)
                    cambios.append("rol")
                    antes["rol"] = rol_anterior
                if cambios:
                    registrar(
                        request, RegistroAuditoria.USUARIO_EDICION, elemento=f"Usuario {empleado.username}",
                        anterior="\n".join(f"{form.fields[c].label}: {antes[c] or ''}" for c in cambios),
                        nuevo="\n".join(f"{form.fields[c].label}: {form.cleaned_data[c] or ''}" for c in cambios),
                    )
            if cambios:
                messages.success(request, f"Se guardaron los cambios de «{empleado}».")
            return redirect("cuentas:editar", pk=empleado.pk)
    return render(request, "cuentas/empleado_detalle.html", {
        "empleado": empleado,
        "form": form,
        "form_password": RestablecerPasswordForm(empleado),
        "es_yo": empleado == request.user,
        "ventas_cobradas": empleado.ventas.filter(estado="PAGADA").count(),
    })


@require_POST
@rol_requerido(roles.ADMINISTRADOR)
def empleado_password(request, pk):
    #RF-USR-05: restablece la contraseña y obliga a cambiarla en el siguiente inicio de sesion
    empleado = get_object_or_404(Usuario, pk=pk)
    if empleado == request.user:
        messages.error(request, "Para cambiar tu propia contraseña usa la opción Cambiar contraseña de tu menu")
        return redirect("cuentas:editar", pk=empleado.pk)
    form = RestablecerPasswordForm(empleado, request.POST)
    if form.is_valid():
        with transaction.atomic():
            empleado = form.save(commit=False)
            empleado.debe_cambiar_password = True
            # Restablecer tambien quita un bloqueo por intentos fallidos
            empleado.intentos_fallidos = 0
            empleado.bloqueado_hasta = None
            empleado.save()
            registrar(
                request, RegistroAuditoria.USUARIO_PASSWORD, elemento=f"Usuario {empleado.username}",
                nuevo="Contraseña temporal asignada",
            )
        messages.success(request, f"Se restableció la contraseña de «{empleado}». Dasela en persona, tendrá que cambiarla al entrar")
    else:
        for errores in form.errors.values():
            for error in errores:
                messages.error(request, error)
    return redirect("cuentas:editar", pk=empleado.pk)


@require_POST
@rol_requerido(roles.ADMINISTRADOR)
def empleado_estado(request, pk):
    #RF-USR-04: activar o desactivar, los empleados nunca se borran
    empleado = get_object_or_404(Usuario, pk=pk)
    try:
        if empleado == request.user:
            raise ErrorEmpleados("No puedes desactivar tu propia cuenta.")
        if empleado.is_active:
            validar_queda_un_administrador(empleado, desactivar=True)
    except ErrorEmpleados as error:
        messages.error(request, str(error))
        return redirect("cuentas:editar", pk=empleado.pk)

    empleado.is_active = not empleado.is_active
    empleado.save(update_fields=["is_active"])
    registrar(
        request, RegistroAuditoria.USUARIO_ESTADO, elemento=f"Usuario {empleado.username}",
        anterior="Inactivo" if empleado.is_active else "Activo",
        nuevo="Activo" if empleado.is_active else "Inactivo",
    )
    if empleado.is_active:
        messages.success(request, f"«{empleado}» se reactivó y ya puede iniciar sesión")
    else:
        messages.success(request, f"«{empleado}» se desactivo, ya no puede iniciar sesión, pero sus ventas se conservan")
    return redirect("cuentas:editar", pk=empleado.pk)


@require_POST
@rol_requerido(roles.ADMINISTRADOR)
def empleado_desbloquear(request, pk):
    #Quita el bloqueo por intentos fallidos (RF-AUT-04) sin esperar los 15 minutos
    empleado = get_object_or_404(Usuario, pk=pk)
    if empleado.esta_bloqueado:
        empleado.intentos_fallidos = 0
        empleado.bloqueado_hasta = None
        empleado.save(update_fields=["intentos_fallidos", "bloqueado_hasta"])
        registrar(
            request, RegistroAuditoria.USUARIO_ESTADO, elemento=f"Usuario {empleado.username}",
            anterior="Bloqueado por intentos fallidos", nuevo="Desbloqueado",
        )
        messages.success(request, f"Se desbloqueó la cuenta de «{empleado}».")
    return redirect("cuentas:editar", pk=empleado.pk)
