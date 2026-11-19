"""
Pruebas de Three Dots, la bitacora de auditoria casos CP-AUD de la ERS
se ejecuta con:  python manage.py test auditoria
"""
from datetime import timedelta

from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from configuracion.models import ConfiguracionNegocio
from cuentas import roles
from cuentas.models import Usuario

from .models import RegistroAuditoria
from .servicios import registrar

PASSWORD = "ClaveSegura2026"


def crear_usuario(nombre, rol):
    usuario = Usuario.objects.create_user(nombre, password=PASSWORD)
    usuario.groups.add(Group.objects.get_or_create(name=rol)[0])
    return usuario


class ThreeDotsTests(TestCase):
    def setUp(self):
        ConfiguracionNegocio(nombre_comercial="Abarrotes Don Pepe").save()
        self.admin = crear_usuario("admin", roles.ADMINISTRADOR)
        self.encargado = crear_usuario("encargado", roles.ENCARGADO)
        self.cajero = crear_usuario("cajero", roles.CAJERO)
        self.client.login(username="admin", password=PASSWORD)  # genera un LOGIN_OK
        registrar(None, RegistroAuditoria.CAMBIO_PRECIO, elemento="Coca-Cola 600", anterior="17.50", nuevo="19.00", usuario=self.encargado)
        registrar(None, RegistroAuditoria.LOGIN_FALLIDO, elemento="Inicio de sesión", usuario_texto="intruso")

    def get(self, **params):
        return self.client.get(reverse("auditoria:bitacora"), params)

    def test_rf_aud_05_solo_el_administrador_la_ve(self):
        self.assertEqual(self.get().status_code, 200)
        for nombre in ("encargado", "cajero"):
            self.client.login(username=nombre, password=PASSWORD)
            # 404 y no 403 para no revelar que la pagina existe
            self.assertEqual(self.get().status_code, 404)
            self.assertEqual(self.client.get(reverse("auditoria:exportar")).status_code, 404)
        self.client.logout()
        self.assertEqual(self.get().status_code, 404)

    def test_menu_three_dots_solo_para_admin(self):
        self.assertContains(self.get(), "Three Dots")
        self.client.login(username="encargado", password=PASSWORD)
        self.assertNotContains(self.client.get(reverse("productos:catalogo")), "Three Dots")

    def test_rf_aud_03_muestra_eventos_con_valores(self):
        r = self.get()
        self.assertContains(r, "Cambio de precio")
        self.assertContains(r, "17.50")
        self.assertContains(r, "19.00")
        self.assertContains(r, "intruso")
        self.assertEqual(r.context["fallidos_hoy"], 1)

    def test_filtro_por_categoria(self):
        r = self.get(categoria="productos")
        self.assertEqual([x.accion for x in r.context["pagina"]], [RegistroAuditoria.CAMBIO_PRECIO])
        r = self.get(categoria="alertas")
        self.assertEqual(
            {x.accion for x in r.context["pagina"]},
            {RegistroAuditoria.CAMBIO_PRECIO, RegistroAuditoria.LOGIN_FALLIDO},
        )

    def test_filtro_por_usuario_y_busqueda(self):
        r = self.get(usuario=self.encargado.pk)
        self.assertEqual(len(r.context["pagina"]), 1)
        r = self.get(q="coca")
        self.assertEqual(len(r.context["pagina"]), 1)
        r = self.get(q="intruso")
        self.assertEqual(r.context["pagina"][0].accion, RegistroAuditoria.LOGIN_FALLIDO)

    def test_filtro_por_fecha(self):
        RegistroAuditoria.objects.filter(accion=RegistroAuditoria.CAMBIO_PRECIO).update(
            fecha=timezone.now() - timedelta(days=40)
        )
        self.assertNotIn(RegistroAuditoria.CAMBIO_PRECIO, [x.accion for x in self.get().context["pagina"]])
        r = self.get(periodo="todo")
        self.assertIn(RegistroAuditoria.CAMBIO_PRECIO, [x.accion for x in r.context["pagina"]])
        hace_40 = (timezone.localdate() - timedelta(days=40)).isoformat()
        r = self.get(desde=hace_40, hasta=hace_40)
        self.assertEqual([x.accion for x in r.context["pagina"]], [RegistroAuditoria.CAMBIO_PRECIO])

    def test_filtro_por_accion(self):
        r = self.get(accion=RegistroAuditoria.LOGIN_FALLIDO)
        self.assertEqual([x.usuario_texto for x in r.context["pagina"]], ["intruso"])
        self.assertContains(r, "Solo «Inicio de sesión fallido»")

    def test_post_de_otro_rol_sigue_dando_404(self):
        self.client.login(username="cajero", password=PASSWORD)
        self.assertEqual(self.client.post(reverse("auditoria:bitacora")).status_code, 404)

    def test_exportar_csv(self):
        r = self.client.get(reverse("auditoria:exportar"), {"categoria": "productos"})
        self.assertEqual(r["Content-Type"], "text/csv; charset=utf-8")
        contenido = r.content.decode("utf-8-sig")
        self.assertIn("Cambio de precio", contenido)
        self.assertIn("encargado", contenido)
        self.assertNotIn("intruso", contenido)

    def test_rf_aud_04_solo_lectura(self):
        """La pantalla no acepta POST y el admin de Django no deja editar ni borrar."""
        self.assertEqual(self.client.post(reverse("auditoria:bitacora")).status_code, 405)
        total = RegistroAuditoria.objects.count()
        from django.contrib.admin.sites import site
        modelo_admin = site._registry[RegistroAuditoria]
        self.assertFalse(modelo_admin.has_change_permission(None))
        self.assertFalse(modelo_admin.has_delete_permission(None))
        self.assertEqual(RegistroAuditoria.objects.count(), total)
