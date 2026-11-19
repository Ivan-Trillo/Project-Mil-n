from django.urls import path

from . import views

app_name = "auditoria"

urlpatterns = [
    path("", views.bitacora, name="bitacora"),
    path("exportar/", views.exportar, name="exportar"),
]
