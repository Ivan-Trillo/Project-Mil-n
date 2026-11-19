from django.urls import path

from . import views

app_name = "cuentas"

urlpatterns = [
    path("contrasena/", views.CambiarPasswordView.as_view(), name="cambiar_password"),
    # Empleados (solo admin)
    path("empleados/", views.empleados, name="usuarios"),
    path("empleados/nuevo/", views.empleado_nuevo, name="nuevo"),
    path("empleados/<int:pk>/", views.empleado_editar, name="editar"),
    path("empleados/<int:pk>/contrasena/", views.empleado_password, name="password"),
    path("empleados/<int:pk>/estado/", views.empleado_estado, name="estado"),
    path("empleados/<int:pk>/desbloquear/", views.empleado_desbloquear, name="desbloquear"),
]
