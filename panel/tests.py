"""
Pruebas del panel de control (Dashboard)

Ejecutar con:  python manage.py test panel
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from configuracion.models import ConfiguracionNegocio
from cuentas import roles
from cuentas.models import Usuario
from productos.models import Producto
from ventas import servicios as caja
from ventas.models import Venta

from . import servicios

PASSWORD = "ClaveSegura2026"


def crear_usuario(nombre, rol):
    usuario = Usuario.objects.create_user(nombre, password=PASSWORD)
    usuario.groups.add(Group.objects.get_or_create(name=rol)[0])
    return usuario


class DashboardTests(TestCase):
    def setUp(self):
        ConfiguracionNegocio(nombre_comercial="Abarrotes Don Pepe", tasa_impuesto=Decimal("16")).save()
        self.cajero = crear_usuario("cajero", roles.CAJERO)
        self.encargado = crear_usuario("encargado", roles.ENCARGADO)
        self.coca = Producto.objects.create(sku="COCA", nombre="Coca-Cola 600", precio_venta=Decimal("17.50"), existencia=50, existencia_minima=5)
        self.pan = Producto.objects.create(sku="PAN", nombre="Pan blanco", precio_venta=Decimal("52.50"), existencia=50, existencia_minima=5)
        self.client.login(username="encargado", password=PASSWORD)

    def vender(self, *lineas, dias_atras=0):
        venta = caja.nuevo_ticket(self.cajero)
        for producto, cantidad in lineas:
            caja.agregar_producto(venta, producto, cantidad)
        venta = caja.cobrar(venta, Decimal("1000"))
        if dias_atras:
            Venta.objects.filter(pk=venta.pk).update(fecha_cobro=venta.fecha_cobro - timedelta(days=dias_atras))
        return venta

    def test_resumen_del_dia(self):
        self.vender((self.coca, 2), (self.pan, 1))  # 87.50, 3 piezas
        self.vender((self.pan, 2))                  # 105.00, 2 piezas
        r = servicios.resumen_dia(timezone.localdate())
        self.assertEqual(r["total"], Decimal("192.50"))
        self.assertEqual(r["num_ventas"], 2)
        self.assertEqual(r["promedio"], Decimal("96.25"))
        self.assertEqual(r["piezas"], 5)

    def test_canceladas_y_pendientes_no_cuentan(self):
        venta = self.vender((self.pan, 1))
        caja.cancelar_venta(venta, self.encargado, "Devolución")
        pendiente = caja.nuevo_ticket(self.cajero)
        caja.agregar_producto(pendiente, self.coca, 3)
        r = servicios.resumen_dia(timezone.localdate())
        self.assertEqual((r["total"], r["num_ventas"], r["piezas"]), (Decimal("0.00"), 0, 0))

    def test_variacion_contra_ayer(self):
        self.assertEqual(servicios.variacion(Decimal("150"), Decimal("100")), {"porcentaje": 50, "direccion": "sube"})
        self.assertEqual(servicios.variacion(Decimal("75"), Decimal("100")), {"porcentaje": 25, "direccion": "baja"})
        self.assertEqual(servicios.variacion(Decimal("0"), Decimal("940")), {"porcentaje": 100, "direccion": "baja"})
        self.assertIsNone(servicios.variacion(Decimal("75"), Decimal("0")))

    def test_variacion_se_muestra_bien(self):
        """Ningún pedazo de código de la plantilla debe aparecer en la pantalla."""
        self.vender((self.pan, 2), dias_atras=1)
        r = self.client.get(reverse("panel:inicio"))
        self.assertContains(r, "100% vs ayer")
        for codigo in ("{#", "#}", "{{", "}}", "{%", "%}"):
            self.assertNotContains(r, codigo)

    def test_ventas_por_dia_incluye_dias_vacios(self):
        self.vender((self.pan, 2))                 # hoy 105.00
        self.vender((self.coca, 2), dias_atras=3)  # hace 3 días 35.00
        hoy = timezone.localdate()
        dias = servicios.ventas_por_dia(hoy - timedelta(days=6), hoy)
        self.assertEqual(len(dias), 7)
        self.assertEqual(dias[-1]["total"], Decimal("105.00"))
        self.assertEqual(dias[-1]["altura"], 100)
        self.assertEqual(dias[-4]["total"], Decimal("35.00"))
        self.assertEqual(dias[-4]["altura"], 33)
        self.assertEqual(dias[0]["altura"], 0)

    def test_mas_vendidos(self):
        self.vender((self.coca, 5), (self.pan, 1))
        self.vender((self.pan, 2))
        hoy = timezone.localdate()
        top = servicios.mas_vendidos(hoy, hoy)
        self.assertEqual([(p["producto__nombre"], p["piezas"]) for p in top], [("Coca-Cola 600", 5), ("Pan blanco", 3)])

    def test_rf_das_03_existencia_baja(self):
        Producto.objects.filter(pk=self.coca.pk).update(existencia=5)
        bajos, total = servicios.existencia_baja()
        self.assertEqual(total, 1)
        self.assertEqual(list(bajos), [self.coca])

    def test_pantalla_del_dashboard(self):
        self.vender((self.coca, 2))
        for periodo in ("7", "30", "mes", "otro"):
            r = self.client.get(reverse("panel:inicio"), {"periodo": periodo})
            self.assertEqual(r.status_code, 200)
        self.assertContains(r, "$35.00")
        self.assertContains(r, "Coca-Cola 600")

    def test_dashboard_sin_ventas(self):
        r = self.client.get(reverse("panel:inicio"))
        self.assertContains(r, "Todavía no hay ventas en este periodo")

    def test_encargado_llega_al_dashboard(self):
        self.assertRedirects(self.client.get(reverse("inicio")), reverse("panel:inicio"))

    def test_cajero_no_ve_el_dashboard(self):
        self.client.login(username="cajero", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("panel:inicio")).status_code, 403)
        self.assertRedirects(self.client.get(reverse("inicio")), reverse("ventas:caja"))

    def test_fechas_en_espanol_aunque_el_navegador_este_en_ingles(self):
        self.vender((self.pan, 1))
        r = self.client.get(reverse("panel:inicio"), HTTP_ACCEPT_LANGUAGE="en-US,en;q=0.9")
        texto = r.content.decode()
        nombres_ingles = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
                          "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
        self.assertFalse([n for n in nombres_ingles if n in texto])
        self.assertIn(" de ", texto)
