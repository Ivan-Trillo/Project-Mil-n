"""
Pruebas del módulo de configuración (casos CP-CFG de la ERS)

Ejecutar con:  python manage.py test configuracion
"""
from decimal import Decimal

from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from auditoria.models import RegistroAuditoria
from cuentas import roles
from cuentas.models import Usuario

from .models import ConfiguracionNegocio

PASSWORD = "ClaveSegura2026"

DATOS = {
    "nombre_comercial": "Abarrotes Don Pepe",
    "razon_social": "José Pérez López",
    "rfc": "pelj800101ab1",
    "direccion": "Av. Ejército Mexicano 123, Mazatlán",
    "telefono": "6691234567",
    "tasa_impuesto": "16.00",
    "mensaje_ticket": "¡Gracias por su compra!",
}


def crear_usuario(nombre, rol):
    usuario = Usuario.objects.create_user(nombre, password=PASSWORD)
    usuario.groups.add(Group.objects.get_or_create(name=rol)[0])
    return usuario


class ConfiguracionTests(TestCase):
    def setUp(self):
        crear_usuario("admin", roles.ADMINISTRADOR)
        crear_usuario("cajero", roles.CAJERO)
        self.url = reverse("configuracion:negocio")

    def test_cp_cfg_04_admin_sin_configuracion_es_redirigido(self):
        self.client.login(username="admin", password=PASSWORD)
        r = self.client.get(reverse("inicio"))
        self.assertRedirects(r, self.url)

    def test_cp_cfg_04_cajero_no_es_redirigido(self):
        self.client.login(username="cajero", password=PASSWORD)
        # El cajero va a su caja, no a la configuración
        self.assertRedirects(self.client.get(reverse("inicio")), reverse("ventas:caja"))

    def test_cp_cfg_01_guardar_datos(self):
        self.client.login(username="admin", password=PASSWORD)
        r = self.client.post(self.url, DATOS)
        self.assertRedirects(r, reverse("inicio"), fetch_redirect_response=False)
        config = ConfiguracionNegocio.obtener()
        self.assertEqual(config.nombre_comercial, "Abarrotes Don Pepe")
        self.assertEqual(config.rfc, "PELJ800101AB1")  #se guarda en mayusculas
        self.assertEqual(config.tasa_impuesto, Decimal("16.00"))
        #ya no redirige y el nombre aparece en la barra
        self.assertContains(self.client.get(reverse("inicio"), follow=True), "Abarrotes Don Pepe")

    def test_rfc_invalido(self):
        self.client.login(username="admin", password=PASSWORD)
        r = self.client.post(self.url, {**DATOS, "rfc": "ABC123"})
        self.assertContains(r, "El RFC no tiene un formato válido")
        self.assertIsNone(ConfiguracionNegocio.obtener())

    def test_tasa_fuera_de_rango(self):
        self.client.login(username="admin", password=PASSWORD)
        self.client.post(self.url, {**DATOS, "tasa_impuesto": "150"})
        self.assertIsNone(ConfiguracionNegocio.obtener())

    def test_cambio_queda_en_bitacora(self):
        self.client.login(username="admin", password=PASSWORD)
        self.client.post(self.url, DATOS)
        self.client.post(self.url, {**DATOS, "tasa_impuesto": "8.00"})
        registro = RegistroAuditoria.objects.filter(accion=RegistroAuditoria.CONFIGURACION).first()
        self.assertIn("16.00", registro.valor_anterior)
        self.assertIn("8.00", registro.valor_nuevo)

    def test_cajero_no_puede_entrar(self):
        self.client.login(username="cajero", password=PASSWORD)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_un_solo_registro(self):
        ConfiguracionNegocio(nombre_comercial="A").save()
        ConfiguracionNegocio(nombre_comercial="B").save()
        self.assertEqual(ConfiguracionNegocio.objects.count(), 1)
