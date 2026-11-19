"""Rutas principales del sistema. Cada módulo agrega las suyas con include()."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from cuentas.forms import InicioSesionForm

urlpatterns = [
    path("admin/", admin.site.urls),
    # RF-AUT-01 y RF-AUT-02
    path(
        "iniciar-sesion/",
        auth_views.LoginView.as_view(
            form_class=InicioSesionForm,
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    path("cerrar-sesion/", auth_views.LogoutView.as_view(), name="logout"),
    path("cuentas/", include("cuentas.urls")),
    path("configuracion/", include("configuracion.urls")),
    path("inventario/", include("productos.urls")),
    path("proveedores/", include("productos.urls_proveedores")),
    path("ventas/", include("ventas.urls")),
    path("dashboard/", include("panel.urls")),
    #el menu de three-dots solo la muestra al admin y a los demas les responde 404
    path("three-dots/", include("auditoria.urls")),
    path("", include("core.urls")),
]

#en desarrollo Django sirve las fotos de productos en producción lo hace el servidor web
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
