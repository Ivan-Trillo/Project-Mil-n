"""
Pruebas del modulo de ventas (casos CP-VEN de la ERS)

Ejecutar con:  python manage.py test ventas
"""
import json
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from configuracion.models import ConfiguracionNegocio
from cuentas import roles
from cuentas.models import Usuario
from productos.models import MovimientoInventario, Producto

from . import servicios
from .models import Venta
from .servicios import ErrorCaja

PASSWORD = "ClaveSegura2026"


def crear_usuario(nombre, rol):
    usuario = Usuario.objects.create_user(nombre, password=PASSWORD)
    usuario.groups.add(Group.objects.get_or_create(name=rol)[0])
    return usuario


class BaseVentas(TestCase):
    def setUp(self):
        ConfiguracionNegocio(nombre_comercial="Abarrotes Don Pepe", tasa_impuesto=Decimal("16")).save()
        self.cajero = crear_usuario("cajero", roles.CAJERO)
        self.coca = Producto.objects.create(sku="COCA", codigo_barras="7501055300075", nombre="Coca-Cola 600", precio_venta=Decimal("17.50"), existencia=3)
        self.pan = Producto.objects.create(sku="PAN", codigo_barras="7501000111206", nombre="Pan blanco", precio_venta=Decimal("52.50"), existencia=10)
        self.venta = servicios.nuevo_ticket(self.cajero)


class ServiciosTests(BaseVentas):
    def test_cp_ven_01_agregar_por_codigo(self):
        servicios.agregar_producto(self.venta, servicios.buscar_por_codigo("7501055300075"))
        servicios.agregar_producto(self.venta, servicios.buscar_por_codigo("7501055300075"))
        detalle = self.venta.detalles.get()
        self.assertEqual(detalle.cantidad, 2)  # si ya estaba, aumenta en 1

    def test_cp_ven_02_codigo_inexistente(self):
        self.assertIsNone(servicios.buscar_por_codigo("000000"))

    def test_producto_inactivo_no_se_vende(self):
        self.coca.activo = False
        self.coca.save()
        self.assertIsNone(servicios.buscar_por_codigo("7501055300075"))
        with self.assertRaises(ErrorCaja):
            servicios.agregar_producto(self.venta, self.coca)

    def test_cp_ven_04_agregar_varios(self):
        servicios.agregar_producto(self.venta, self.pan, 6)
        self.assertEqual(self.venta.detalles.get().cantidad, 6)

    def test_cp_ven_07_no_supera_existencia(self):
        with self.assertRaises(ErrorCaja):
            servicios.agregar_producto(self.venta, self.coca, 5)
        self.assertFalse(self.venta.detalles.exists())

    def test_cp_ven_05_06_cambiar_y_borrar(self):
        d = servicios.agregar_producto(self.venta, self.pan)
        servicios.cambiar_cantidad(self.venta, d.pk, 4)
        self.venta.refresh_from_db()
        self.assertEqual(self.venta.total, Decimal("210.00"))
        servicios.quitar_producto(self.venta, d.pk)
        self.venta.refresh_from_db()
        self.assertEqual(self.venta.total, Decimal("0.00"))

    def test_cp_ven_08_totales_e_iva_incluido(self):
        servicios.agregar_producto(self.venta, self.coca, 2)   # 35.00
        servicios.agregar_producto(self.venta, self.pan, 1)    # 52.50
        self.venta.refresh_from_db()
        self.assertEqual(self.venta.total, Decimal("87.50"))
        # 87.50 * 16 / 116 = 12.068... -> 12.07
        self.assertEqual(self.venta.impuesto, Decimal("12.07"))

    def test_rf_cfg_02_iva_116(self):
        p = Producto.objects.create(sku="X", nombre="X", precio_venta=Decimal("116.00"), existencia=1)
        servicios.agregar_producto(self.venta, p)
        self.venta.refresh_from_db()
        self.assertEqual(self.venta.impuesto, Decimal("16.00"))

    def test_descuento(self):
        servicios.agregar_producto(self.venta, self.pan, 2)  # 105.00
        servicios.aplicar_descuento(self.venta, Decimal("5"))
        self.venta.refresh_from_db()
        self.assertEqual((self.venta.subtotal, self.venta.descuento, self.venta.total), (Decimal("105.00"), Decimal("5.00"), Decimal("100.00")))
        with self.assertRaises(ErrorCaja):
            servicios.aplicar_descuento(self.venta, Decimal("200"))

    def test_cp_ven_11_cobro_y_cambio(self):
        servicios.agregar_producto(self.venta, self.coca, 2)
        servicios.agregar_producto(self.venta, self.pan, 1)
        venta = servicios.cobrar(self.venta, Decimal("100.00"))
        self.assertEqual(venta.estado, Venta.PAGADA)
        self.assertEqual(venta.cambio, Decimal("12.50"))  # el ejemplo de la ERS
        self.coca.refresh_from_db()
        self.pan.refresh_from_db()
        self.assertEqual((self.coca.existencia, self.pan.existencia), (1, 9))
        self.assertEqual(MovimientoInventario.objects.filter(venta=venta, tipo=MovimientoInventario.VENTA).count(), 2)

    def test_cp_ven_12_monto_insuficiente(self):
        servicios.agregar_producto(self.venta, self.pan)
        with self.assertRaises(ErrorCaja):
            servicios.cobrar(self.venta, Decimal("50.00"))
        self.venta.refresh_from_db()
        self.assertEqual(self.venta.estado, Venta.PENDIENTE)

    def test_cp_ven_13_cobro_atomico(self):
        """Si falla algo a la mitad del cobro no queda ni la venta ni el descuento de inventario."""
        servicios.agregar_producto(self.venta, self.coca, 2)
        servicios.agregar_producto(self.venta, self.pan, 1)
        with mock.patch("ventas.servicios.SecuenciaFolio.siguiente", side_effect=RuntimeError("falla simulada")):
            with self.assertRaises(RuntimeError):
                servicios.cobrar(self.venta, Decimal("100"))
        self.venta.refresh_from_db()
        self.coca.refresh_from_db()
        self.pan.refresh_from_db()
        self.assertEqual(self.venta.estado, Venta.PENDIENTE)
        self.assertIsNone(self.venta.folio)
        self.assertEqual((self.coca.existencia, self.pan.existencia), (3, 10))
        self.assertFalse(MovimientoInventario.objects.exists())

    def test_existencia_vendida_por_otra_caja(self):
        """RNF-CON-03: si otra caja vendió antes, el cobro se rechaza y no deja negativos."""
        servicios.agregar_producto(self.venta, self.coca, 3)
        Producto.objects.filter(pk=self.coca.pk).update(existencia=1)
        with self.assertRaises(ErrorCaja):
            servicios.cobrar(self.venta, Decimal("100"))
        self.coca.refresh_from_db()
        self.assertEqual(self.coca.existencia, 1)
        self.assertFalse(Venta.objects.filter(estado=Venta.PAGADA).exists())

    def test_cp_ven_15_folios_consecutivos(self):
        folios = []
        for _ in range(3):
            venta = servicios.nuevo_ticket(self.cajero)
            servicios.agregar_producto(venta, self.pan)
            folios.append(servicios.cobrar(venta, Decimal("100")).folio)
        self.assertEqual(folios, [folios[0], folios[0] + 1, folios[0] + 2])

    def test_precio_se_conserva_en_venta(self):
        """RNF-BD-04: cambiar el precio después no altera la venta."""
        servicios.agregar_producto(self.venta, self.pan)
        venta = servicios.cobrar(self.venta, Decimal("100"))
        Producto.objects.filter(pk=self.pan.pk).update(precio_venta=Decimal("99"))
        self.assertEqual(venta.detalles.get().precio_unitario, Decimal("52.50"))


class ApiCajaTests(BaseVentas):
    def setUp(self):
        super().setUp()
        self.client.login(username="cajero", password=PASSWORD)

    def post(self, nombre, datos=None, **kwargs):
        return self.client.post(reverse(nombre, kwargs=kwargs), json.dumps(datos or {}), content_type="application/json")

    def test_cajero_entra_directo_a_la_caja(self):
        self.assertRedirects(self.client.get(reverse("inicio")), reverse("ventas:caja"))
        self.assertContains(self.client.get(reverse("ventas:caja")), "Escanea o busca un producto")

    def test_flujo_completo(self):
        pk = self.venta.pk
        r = self.post("ventas:api_agregar", {"codigo": "7501055300075"}, pk=pk).json()
        self.assertEqual(r["estado"]["activo"]["lineas"][0]["cantidad"], 1)
        r = self.post("ventas:api_agregar", {"codigo": "3*7501000111206"}, pk=pk).json()  # Agregar varios
        self.assertEqual(r["estado"]["activo"]["total"], "175.00")
        r = self.post("ventas:api_cobrar", {"monto_recibido": "200"}, pk=pk).json()
        self.assertTrue(r["ok"])
        self.assertEqual(r["venta"]["cambio"], "25.00")
        # Después del cobro hay un ticket nuevo vacío
        self.assertEqual(r["estado"]["activo"]["lineas"], [])
        # El ticket impreso tiene los datos del negocio y el folio (RF-VEN-14)
        t = self.client.get(reverse("ventas:ticket", args=[pk]))
        self.assertContains(t, "Abarrotes Don Pepe")
        self.assertContains(t, r["venta"]["folio"])
        self.assertContains(t, "$25.00")

    def test_ticket_se_puede_imprimir_desde_la_caja(self):
        servicios.agregar_producto(self.venta, self.pan)
        venta = servicios.cobrar(self.venta, Decimal("100"))
        r = self.client.get(reverse("ventas:ticket", args=[venta.pk]))
        self.assertEqual(r.headers["X-Frame-Options"], "SAMEORIGIN")
        # La caja en sí sigue sin poder cargarse dentro de otro sitio
        self.assertEqual(self.client.get(reverse("ventas:caja")).headers["X-Frame-Options"], "DENY")

    def test_cp_ven_02_aviso_no_encontrado(self):
        r = self.post("ventas:api_agregar", {"codigo": "999"}, pk=self.venta.pk)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["error"], "Producto no encontrado")

    def test_cp_ven_03_busqueda_por_nombre(self):
        r = self.client.get(reverse("ventas:api_productos"), {"q": "pa"}).json()
        self.assertEqual(r["productos"], [])  # menos de 3 letras
        r = self.client.get(reverse("ventas:api_productos"), {"q": "pan"}).json()
        self.assertEqual([p["nombre"] for p in r["productos"]], ["Pan blanco"])

    def test_cp_ven_09_varios_tickets(self):
        for _ in range(4):
            self.post("ventas:api_nuevo_ticket")
        r = self.client.get(reverse("ventas:api_estado")).json()
        self.assertEqual(len(r["estado"]["tickets"]), 5)

    def test_cp_ven_10_pendiente_se_conserva(self):
        self.post("ventas:api_agregar", {"codigo": "7501055300075"}, pk=self.venta.pk)
        self.post("ventas:api_nuevo_ticket")
        r = self.client.get(reverse("ventas:api_estado"), {"ticket": self.venta.pk}).json()
        self.assertEqual(r["estado"]["activo"]["lineas"][0]["nombre"], "Coca-Cola 600")

    def test_no_puede_tocar_ticket_de_otro(self):
        otro = crear_usuario("otro", roles.CAJERO)
        ajeno = servicios.nuevo_ticket(otro)
        r = self.post("ventas:api_agregar", {"codigo": "7501055300075"}, pk=ajeno.pk)
        self.assertEqual(r.status_code, 400)
        self.assertFalse(ajeno.detalles.exists())

    def test_descartar_ticket(self):
        self.post("ventas:api_descartar", pk=self.venta.pk)
        self.assertFalse(Venta.objects.filter(pk=self.venta.pk).exists())

    def test_cajero_no_ve_tickets_de_otros(self):
        otro = crear_usuario("otro", roles.CAJERO)
        venta = servicios.nuevo_ticket(otro)
        servicios.agregar_producto(venta, self.pan)
        servicios.cobrar(venta, Decimal("100"))
        self.assertEqual(self.client.get(reverse("ventas:ticket", args=[venta.pk])).status_code, 404)


class RegistroTests(BaseVentas):
    """Fase 7: historial de ventas, detalle, cancelación y reimpresión."""

    def setUp(self):
        super().setUp()
        self.encargado = crear_usuario("encargado", roles.ENCARGADO)
        servicios.agregar_producto(self.venta, self.coca, 2)  # 35.00
        servicios.agregar_producto(self.venta, self.pan, 1)   # 52.50
        self.venta = servicios.cobrar(self.venta, Decimal("100"))
        self.client.login(username="encargado", password=PASSWORD)

    def cancelar(self, motivo="El cliente devolvió todo"):
        return self.client.post(reverse("ventas:cancelar", args=[self.venta.pk]), {"motivo": motivo})

    # ---------------------------------------------------------- Cancelación

    def test_rf_ven_17_cancelar_regresa_inventario(self):
        self.cancelar()
        self.venta.refresh_from_db()
        self.coca.refresh_from_db()
        self.pan.refresh_from_db()
        self.assertEqual(self.venta.estado, Venta.CANCELADA)
        self.assertEqual(self.venta.motivo_cancelacion, "El cliente devolvió todo")
        self.assertEqual(self.venta.cancelada_por, self.encargado)
        self.assertIsNotNone(self.venta.fecha_cancelacion)
        self.assertEqual((self.coca.existencia, self.pan.existencia), (3, 10))
        # Un movimiento de cancelación por cada producto, ligado a la venta
        movimientos = MovimientoInventario.objects.filter(venta=self.venta, tipo=MovimientoInventario.CANCELACION)
        self.assertEqual(sorted(m.cantidad for m in movimientos), [1, 2])

    def test_cancelacion_queda_en_la_bitacora(self):
        from auditoria.models import RegistroAuditoria
        self.cancelar()
        registro = RegistroAuditoria.objects.get(accion=RegistroAuditoria.VENTA_CANCELACION)
        self.assertEqual(registro.usuario, self.encargado)
        self.assertIn("El cliente devolvió todo", registro.valor_nuevo)

    def test_cancelacion_sin_motivo_no_procede(self):
        self.cancelar(motivo="   ")
        self.venta.refresh_from_db()
        self.assertEqual(self.venta.estado, Venta.PAGADA)
        self.assertFalse(MovimientoInventario.objects.filter(tipo=MovimientoInventario.CANCELACION).exists())

    def test_no_se_cancela_dos_veces(self):
        self.cancelar()
        self.cancelar()
        self.pan.refresh_from_db()
        self.assertEqual(self.pan.existencia, 10)  # no se regresa dos veces
        self.assertEqual(MovimientoInventario.objects.filter(tipo=MovimientoInventario.CANCELACION).count(), 2)

    def test_cancelacion_atomica(self):
        """Si falla algo a la mitad, la venta sigue pagada y el inventario no cambia."""
        with mock.patch("ventas.servicios.registrar_movimiento", side_effect=[mock.DEFAULT, RuntimeError("falla simulada")]):
            with self.assertRaises(RuntimeError):
                servicios.cancelar_venta(self.venta, self.encargado, "prueba")
        self.venta.refresh_from_db()
        self.assertEqual(self.venta.estado, Venta.PAGADA)

    def test_producto_dado_de_baja_tambien_regresa(self):
        Producto.objects.filter(pk=self.pan.pk).update(activo=False)
        servicios.cancelar_venta(self.venta, self.encargado, "Devolución")
        self.pan.refresh_from_db()
        self.assertEqual(self.pan.existencia, 10)

    def test_ticket_pendiente_no_se_cancela(self):
        pendiente = servicios.nuevo_ticket(self.cajero)
        with self.assertRaises(ErrorCaja):
            servicios.cancelar_venta(pendiente, self.encargado, "x")

    def test_cajero_no_puede_cancelar_ni_ver_registro(self):
        self.client.login(username="cajero", password=PASSWORD)
        self.assertEqual(self.cancelar().status_code, 403)
        self.assertEqual(self.client.get(reverse("ventas:historial")).status_code, 403)
        self.assertEqual(self.client.get(reverse("ventas:detalle", args=[self.venta.pk])).status_code, 403)
        self.venta.refresh_from_db()
        self.assertEqual(self.venta.estado, Venta.PAGADA)

    def test_cancelar_requiere_post(self):
        self.assertEqual(self.client.get(reverse("ventas:cancelar", args=[self.venta.pk])).status_code, 405)

    # ---------------------------------------------------------- Historial y detalle

    def test_historial_muestra_ventas_de_hoy(self):
        r = self.client.get(reverse("ventas:historial"))
        self.assertContains(r, self.venta.folio_texto)
        self.assertEqual(r.context["resumen"]["num_ventas"], 1)
        self.assertEqual(r.context["resumen"]["total"], Decimal("87.50"))

    def test_historial_no_muestra_pendientes(self):
        pendiente = servicios.nuevo_ticket(self.cajero)
        r = self.client.get(reverse("ventas:historial"), {"periodo": "todo"})
        self.assertNotIn(pendiente.pk, [v.pk for v in r.context["pagina"]])

    def test_canceladas_no_suman_al_total(self):
        self.cancelar()
        r = self.client.get(reverse("ventas:historial"))
        self.assertEqual(r.context["resumen"]["num_ventas"], 0)
        self.assertEqual(r.context["resumen"]["total"], Decimal("0.00"))
        self.assertEqual(r.context["resumen"]["num_canceladas"], 1)
        r = self.client.get(reverse("ventas:historial"), {"estado": "pagadas"})
        self.assertEqual(len(r.context["pagina"]), 0)

    def test_buscar_por_folio_en_todas_las_fechas(self):
        Venta.objects.filter(pk=self.venta.pk).update(fecha_cobro=self.venta.fecha_cobro - timedelta(days=90))
        r = self.client.get(reverse("ventas:historial"))
        self.assertEqual(len(r.context["pagina"]), 0)  # no es de hoy
        r = self.client.get(reverse("ventas:historial"), {"q": self.venta.folio_texto})
        self.assertEqual([v.pk for v in r.context["pagina"]], [self.venta.pk])
        r = self.client.get(reverse("ventas:historial"), {"q": "abc"})
        self.assertEqual(len(r.context["pagina"]), 0)

    def test_filtro_por_rango_y_cajero(self):
        hoy = timezone.localdate().isoformat()
        r = self.client.get(reverse("ventas:historial"), {"desde": hoy, "hasta": hoy, "cajero": self.cajero.pk})
        self.assertEqual(len(r.context["pagina"]), 1)
        r = self.client.get(reverse("ventas:historial"), {"cajero": self.encargado.pk})
        self.assertEqual(len(r.context["pagina"]), 0)

    def test_detalle_de_venta(self):
        r = self.client.get(reverse("ventas:detalle", args=[self.venta.pk]))
        self.assertContains(r, "Coca-Cola 600")
        self.assertContains(r, "$87.50")
        self.assertContains(r, "Cancelar venta")

    def test_detalle_de_venta_cancelada(self):
        self.cancelar()
        r = self.client.get(reverse("ventas:detalle", args=[self.venta.pk]))
        self.assertContains(r, "El cliente devolvió todo")
        self.assertNotContains(r, 'data-bs-target="#modalCancelar"')

    # ---------------------------------------------------------- Reimpresión (RF-VEN-16)

    def test_rf_ven_16_reimpresion_lleva_leyenda(self):
        r = self.client.get(reverse("ventas:ticket", args=[self.venta.pk]), {"copia": "1"})
        self.assertContains(r, "REIMPRESIÓN")
        self.assertContains(r, self.venta.folio_texto)
        original = self.client.get(reverse("ventas:ticket", args=[self.venta.pk]))
        self.assertNotContains(original, "REIMPRESIÓN")

    def test_reimpresion_de_cancelada(self):
        self.cancelar()
        r = self.client.get(reverse("ventas:ticket", args=[self.venta.pk]), {"copia": "1"})
        self.assertContains(r, "VENTA CANCELADA")

    def test_menu_registro_no_se_marca_en_la_caja(self):
        r = self.client.get(reverse("ventas:caja"))
        self.assertEqual([o["texto"] for o in r.context["menu"] if o["activa"]], ["Caja"])
        r = self.client.get(reverse("ventas:detalle", args=[self.venta.pk]))
        self.assertEqual([o["texto"] for o in r.context["menu"] if o["activa"]], ["Registro"])
