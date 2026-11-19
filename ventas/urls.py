from django.urls import path

from . import views

app_name = "ventas"

urlpatterns = [
    path("caja/", views.caja, name="caja"),
    path("caja/api/estado/", views.api_estado, name="api_estado"),
    path("caja/api/productos/", views.api_productos, name="api_productos"),
    path("caja/api/tickets/", views.api_nuevo_ticket, name="api_nuevo_ticket"),
    path("caja/api/tickets/<int:pk>/descartar/", views.api_descartar, name="api_descartar"),
    path("caja/api/tickets/<int:pk>/agregar/", views.api_agregar, name="api_agregar"),
    path("caja/api/tickets/<int:pk>/lineas/<int:detalle_id>/cantidad/", views.api_cantidad, name="api_cantidad"),
    path("caja/api/tickets/<int:pk>/lineas/<int:detalle_id>/quitar/", views.api_quitar, name="api_quitar"),
    path("caja/api/tickets/<int:pk>/descuento/", views.api_descuento, name="api_descuento"),
    path("caja/api/tickets/<int:pk>/cobrar/", views.api_cobrar, name="api_cobrar"),
    path("<int:pk>/ticket/", views.ticket_impreso, name="ticket"),
    # Registro (historial de ventas)
    path("registro/", views.historial, name="historial"),
    path("registro/<int:pk>/", views.venta_detalle, name="detalle"),
    path("registro/<int:pk>/cancelar/", views.venta_cancelar, name="cancelar"),
]
