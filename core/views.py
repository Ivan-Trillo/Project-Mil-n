from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from cuentas import roles


@login_required
def inicio(request):

    #Pantalla de inicio el Encargado y el admin llegan al Dashboard, el cajero va directo a la caja
    if request.user.tiene_rol(*roles.GESTION):
        return redirect("panel:inicio")
    if request.user.tiene_rol(roles.CAJERO):
        return redirect("ventas:caja")
    return render(request, "core/inicio.html")
