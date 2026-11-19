from django.urls import path

from . import views

app_name = "productos"

urlpatterns = [
    path("", views.catalogo, name="catalogo"),
    path("nuevo/", views.producto_nuevo, name="nuevo"),
    path("<int:pk>/", views.producto_detalle, name="detalle"),
    path("<int:pk>/editar/", views.producto_editar, name="editar"),
    path("<int:pk>/estado/", views.producto_estado, name="estado"),
    path("<int:pk>/movimiento/", views.producto_movimiento, name="movimiento"),
    path("categorias/", views.categorias, name="categorias"),
    path("categorias/<int:pk>/", views.categorias, name="categoria_editar"),
    path("categorias/<int:pk>/estado/", views.categoria_estado, name="categoria_estado"),
]
