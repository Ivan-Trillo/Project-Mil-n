from django.contrib import messages
from django.shortcuts import redirect, render

from auditoria.models import RegistroAuditoria
from auditoria.servicios import registrar
from cuentas import roles
from cuentas.permisos import rol_requerido

from .forms import ConfiguracionNegocioForm
from .models import ConfiguracionNegocio


@rol_requerido(roles.ADMINISTRADOR)
def negocio(request):
    """RF-CFG-01 a RF-CFG-04: datos del negocio, solo para el Administrador."""
    actual = ConfiguracionNegocio.obtener()
    es_primera_vez = actual is None
    form = ConfiguracionNegocioForm(request.POST or None, instance=actual)

    if request.method == "POST" and form.is_valid():
        #guarda en la bitacora que campos cambiaron, con su valor anterior y nuevo
        cambios_antes, cambios_despues = [], []
        for nombre in form.changed_data:
            etiqueta = form.fields[nombre].label
            anterior = form.initial.get(nombre, "")
            cambios_antes.append(f"{etiqueta}: {anterior}")
            cambios_despues.append(f"{etiqueta}: {form.cleaned_data[nombre]}")
        form.save()
        if cambios_despues:
            registrar(
                request,
                RegistroAuditoria.CONFIGURACION,
                elemento="Configuración del negocio",
                anterior="\n".join(cambios_antes),
                nuevo="\n".join(cambios_despues),
            )
        messages.success(request, "La configuración del negocio se guardó correctamente.")
        return redirect("inicio" if es_primera_vez else "configuracion:negocio")

    return render(request, "configuracion/negocio.html", {
        "form": form,
        "es_primera_vez": es_primera_vez,
    })
