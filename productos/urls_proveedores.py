from django.urls import path

from . import views

app_name = "proveedores"

urlpatterns = [
    path("", views.proveedores, name="lista"),
    path("nuevo/", views.proveedor_form, name="nuevo"),
    path("<int:pk>/", views.proveedor_form, name="editar"),
    path("<int:pk>/estado/", views.proveedor_estado, name="estado"),
]
