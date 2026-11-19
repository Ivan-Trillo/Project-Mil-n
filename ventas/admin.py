from django.contrib import admin

from .models import DetalleVenta, Venta


class DetalleVentaInline(admin.TabularInline):
    model = DetalleVenta
    extra = 0
    readonly_fields = ("producto", "cantidad", "precio_unitario", "subtotal")
    can_delete = False


@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display = ("folio", "estado", "usuario", "fecha_cobro", "total")
    list_filter = ("estado",)
    search_fields = ("folio",)
    inlines = [DetalleVentaInline]

    def has_delete_permission(self, request, obj=None):
        return False
