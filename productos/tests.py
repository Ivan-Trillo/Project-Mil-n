"""
Pruebas del modulo de productos e inventario (casos CP-PRO de la ERS)

Ejecutar con:  python manage.py test productos
"""
from decimal import Decimal

from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from auditoria.models import RegistroAuditoria
from configuracion.models import ConfiguracionNegocio
from cuentas import roles
from cuentas.models import Usuario

from .models import Categoria, MovimientoInventario, Producto
from .servicios import ExistenciaInsuficiente, registrar_movimiento

PASSWORD = "ClaveSegura2026"


def crear_usuario(nombre, rol):
    usuario = Usuario.objects.create_user(nombre, password=PASSWORD)
    usuario.groups.add(Group.objects.get_or_create(name=rol)[0])
    return usuario


def datos_producto(**cambios):
    datos = {
        "nombre": "Coca-Cola 600 ml",
        "codigo_barras": "7501055300075",
        "sku": "coca600",
        "precio_venta": "18.50",
        "costo": "13.00",
        "existencia": "24",
        "existencia_minima": "6",
        "descripcion": "",
    }
    datos.update(cambios)
    return datos


class BaseProductos(TestCase):
    def setUp(self):
        ConfiguracionNegocio(nombre_comercial="Tienda").save()
        self.encargado = crear_usuario("encargado", roles.ENCARGADO)
        self.cajero = crear_usuario("cajero", roles.CAJERO)
        self.client.login(username="encargado", password=PASSWORD)

    def crear(self, **cambios):
        return self.client.post(reverse("productos:nuevo"), datos_producto(**cambios))


class AltaProductoTests(BaseProductos):
    def test_cp_pro_01_registrar_producto(self):
        r = self.crear()
        self.assertRedirects(r, reverse("productos:catalogo"))
        p = Producto.objects.get(sku="COCA600")  # el SKU se guarda en mayusculas
        self.assertEqual(p.existencia, 24)
        self.assertEqual(p.precio_venta, Decimal("18.50"))
        # La existencia inicial queda como primer movimiento del historial
        mov = p.movimientos.get()
        self.assertEqual((mov.tipo, mov.cantidad, mov.existencia_resultante), (MovimientoInventario.ENTRADA, 24, 24))
        self.assertTrue(RegistroAuditoria.objects.filter(accion=RegistroAuditoria.PRODUCTO_ALTA).exists())

    def test_cp_pro_02_codigo_y_sku_unicos(self):
        self.crear()
        r = self.crear(sku="OTRO")
        self.assertEqual(r.status_code, 200)
        r = self.crear(codigo_barras="123", sku="coca600")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Producto.objects.count(), 1)

    def test_varios_productos_sin_codigo(self):
        self.crear(codigo_barras="", sku="A")
        self.crear(codigo_barras="", sku="B")
        self.assertEqual(Producto.objects.filter(codigo_barras__isnull=True).count(), 2)

    def test_cp_pro_03_validaciones(self):
        self.crear(precio_venta="0")
        self.crear(sku="X", codigo_barras="1", existencia="-5")
        self.assertEqual(Producto.objects.count(), 0)

    def test_cajero_no_puede_registrar(self):
        self.client.login(username="cajero", password=PASSWORD)
        self.assertEqual(self.crear().status_code, 403)


class CatalogoTests(BaseProductos):
    def setUp(self):
        super().setUp()
        bebidas = Categoria.objects.create(nombre="Bebidas")
        Producto.objects.create(sku="A", codigo_barras="111", nombre="Agua 1 L", precio_venta=10, categoria=bebidas, existencia=50)
        Producto.objects.create(sku="B", codigo_barras="222", nombre="Pan blanco", precio_venta=40, existencia=2, existencia_minima=5)
        Producto.objects.create(sku="C", nombre="Producto viejo", precio_venta=5, activo=False)

    def nombres(self, **params):
        r = self.client.get(reverse("productos:catalogo"), params)
        return [p.nombre for p in r.context["pagina"]]

    def test_cp_pro_04_busqueda(self):
        self.assertEqual(self.nombres(q="agua"), ["Agua 1 L"])
        self.assertEqual(self.nombres(q="222"), ["Pan blanco"])
        self.assertEqual(self.nombres(q="b"), ["Pan blanco"])  # por SKU exacto o nombre

    def test_cp_pro_04_filtro_categoria(self):
        categoria = Categoria.objects.get(nombre="Bebidas")
        self.assertEqual(self.nombres(categoria=categoria.pk), ["Agua 1 L"])

    def test_cp_pro_10_existencia_baja(self):
        self.assertEqual(self.nombres(estado="bajos"), ["Pan blanco"])
        self.assertContains(self.client.get(reverse("productos:catalogo")), "1 producto con existencia baja")

    def test_cp_pro_06_inactivos_ocultos(self):
        self.assertNotIn("Producto viejo", self.nombres())
        self.assertEqual(self.nombres(estado="inactivos"), ["Producto viejo"])

    def test_cajero_ve_catalogo_sin_inactivos(self):
        self.client.login(username="cajero", password=PASSWORD)
        self.assertNotIn("Producto viejo", self.nombres(estado="todos"))


class EdicionTests(BaseProductos):
    def setUp(self):
        super().setUp()
        self.crear()
        self.producto = Producto.objects.get()

    def test_cp_pro_05_cambio_de_precio_en_bitacora(self):
        url = reverse("productos:editar", args=[self.producto.pk])
        datos = datos_producto(precio_venta="20.00")
        datos.pop("existencia")
        self.client.post(url, datos)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.precio_venta, Decimal("20.00"))
        registro = RegistroAuditoria.objects.get(accion=RegistroAuditoria.CAMBIO_PRECIO)
        self.assertEqual((registro.valor_anterior, registro.valor_nuevo), ("18.50", "20.00"))

    def test_editar_no_cambia_existencia(self):
        url = reverse("productos:editar", args=[self.producto.pk])
        self.client.post(url, datos_producto(existencia="999"))
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.existencia, 24)

    def test_cp_pro_06_baja_y_reactivacion(self):
        url = reverse("productos:estado", args=[self.producto.pk])
        self.assertEqual(self.client.get(url).status_code, 405)  # solo por POST
        self.client.post(url)
        self.producto.refresh_from_db()
        self.assertFalse(self.producto.activo)
        self.assertTrue(Producto.objects.filter(pk=self.producto.pk).exists())  # no se borra
        self.client.post(url)
        self.producto.refresh_from_db()
        self.assertTrue(self.producto.activo)


class MovimientosTests(BaseProductos):
    def setUp(self):
        super().setUp()
        self.producto = Producto.objects.create(sku="A", nombre="Agua", precio_venta=10, existencia=10)
        self.url = reverse("productos:movimiento", args=[self.producto.pk])

    def test_cp_pro_08_entrada(self):
        self.client.post(self.url, {"tipo": "ENTRADA", "cantidad": 5, "motivo": "Compra"})
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.existencia, 15)
        mov = self.producto.movimientos.get()
        self.assertEqual((mov.cantidad, mov.existencia_resultante, mov.usuario), (5, 15, self.encargado))

    def test_cp_pro_08_ajuste_negativo(self):
        self.client.post(self.url, {"tipo": "AJUSTE", "cantidad": -3, "motivo": "Merma"})
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.existencia, 7)
        self.assertTrue(RegistroAuditoria.objects.filter(accion=RegistroAuditoria.INVENTARIO_AJUSTE).exists())

    def test_ajuste_sin_motivo_rechazado(self):
        self.client.post(self.url, {"tipo": "AJUSTE", "cantidad": -1, "motivo": ""})
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.existencia, 10)

    def test_no_permite_existencia_negativa(self):
        self.client.post(self.url, {"tipo": "AJUSTE", "cantidad": -11, "motivo": "Error"})
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.existencia, 10)
        with self.assertRaises(ExistenciaInsuficiente):
            registrar_movimiento(self.producto, "AJUSTE", -11, self.encargado)
        self.assertEqual(self.producto.movimientos.count(), 0)

    def test_cp_pro_09_historial_en_ficha(self):
        self.client.post(self.url, {"tipo": "ENTRADA", "cantidad": 5, "motivo": "Compra"})
        r = self.client.get(reverse("productos:detalle", args=[self.producto.pk]))
        self.assertContains(r, "Compra")
        self.assertContains(r, "+5")


class CategoriasProveedoresTests(BaseProductos):
    def test_cp_pro_07_categorias(self):
        self.client.post(reverse("productos:categorias"), {"nombre": "Lácteos"})
        categoria = Categoria.objects.get(nombre="Lácteos")
        self.client.post(reverse("productos:categoria_estado", args=[categoria.pk]))
        categoria.refresh_from_db()
        self.assertFalse(categoria.activa)

    def test_proveedores(self):
        r = self.client.post(reverse("proveedores:nuevo"), {"nombre": "Bimbo", "rfc": "bim011108dj5"})
        self.assertRedirects(r, reverse("proveedores:lista"))
        self.assertContains(self.client.get(reverse("proveedores:lista")), "Bimbo")

    def test_cajero_no_ve_proveedores(self):
        self.client.login(username="cajero", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("proveedores:lista")).status_code, 403)
