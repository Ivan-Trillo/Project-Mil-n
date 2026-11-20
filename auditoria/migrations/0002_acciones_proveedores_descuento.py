#agrega a la bitacora las acciones de proveedores y de ventas con descuento (RF-AUD-01)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("auditoria", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="registroauditoria",
            name="accion",
            field=models.CharField(choices=[('LOGIN_OK', 'Inicio de sesión'), ('LOGIN_FALLIDO', 'Inicio de sesión fallido'), ('LOGOUT', 'Cierre de sesión'), ('PRODUCTO_ALTA', 'Alta de producto'), ('PRODUCTO_EDICION', 'Edición de producto'), ('PRODUCTO_BAJA', 'Baja de producto'), ('CAMBIO_PRECIO', 'Cambio de precio'), ('INVENTARIO_AJUSTE', 'Entrada o ajuste de inventario'), ('VENTA_CANCELACION', 'Cancelación de venta'), ('CONFIGURACION', 'Cambio de configuración'), ('USUARIO_ALTA', 'Alta de usuario'), ('USUARIO_EDICION', 'Edición de usuario'), ('USUARIO_ESTADO', 'Activación o desactivación de usuario'), ('USUARIO_PASSWORD', 'Restablecimiento de contraseña'), ('PROVEEDOR_ALTA', 'Alta de proveedor'), ('PROVEEDOR_EDICION', 'Edición de proveedor'), ('PROVEEDOR_ESTADO', 'Activación o desactivación de proveedor'), ('VENTA_DESCUENTO', 'Venta con descuento')], db_index=True, max_length=20, verbose_name="acción"),
        ),
    ]
