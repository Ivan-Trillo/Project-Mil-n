from django.contrib import admin

from .models import RegistroAuditoria


@admin.register(RegistroAuditoria)
class RegistroAuditoriaAdmin(admin.ModelAdmin):
    """Solo lectura: nadie puede crear, editar ni borrar registros (RF-AUD-04)."""

    list_display = ("fecha", "usuario", "usuario_texto", "accion", "elemento", "ip")
    list_filter = ("accion",)
    search_fields = ("usuario__username", "usuario_texto", "elemento")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
