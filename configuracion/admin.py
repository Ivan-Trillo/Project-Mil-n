from django.contrib import admin

from .models import ConfiguracionNegocio


@admin.register(ConfiguracionNegocio)
class ConfiguracionNegocioAdmin(admin.ModelAdmin):
    list_display = ("nombre_comercial", "rfc", "tasa_impuesto", "actualizado")

    def has_delete_permission(self, request, obj=None):
        return False
