from django.contrib import admin

from .models import Categoria, MovimientoInventario, Producto, Proveedor


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "activa")
    list_filter = ("activa",)
    search_fields = ("nombre",)


@admin.register(Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
    list_display = ("nombre", "contacto", "telefono", "correo", "activo")
    list_filter = ("activo",)
    search_fields = ("nombre", "contacto", "rfc")


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "sku", "codigo_barras", "precio_venta", "existencia", "existencia_minima", "activo")
    list_filter = ("activo", "categoria", "proveedor")
    search_fields = ("nombre", "sku", "codigo_barras")


@admin.register(MovimientoInventario)
class MovimientoInventarioAdmin(admin.ModelAdmin):
    list_display = ("fecha", "producto", "tipo", "cantidad", "existencia_resultante", "usuario")
    list_filter = ("tipo",)
    search_fields = ("producto__nombre",)

    #los movimientos solo los crea el sistema
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
