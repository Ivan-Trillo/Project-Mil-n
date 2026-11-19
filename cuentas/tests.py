"""
Pruebas automatizadas del modulo de autenticación casos CP-AUT de la ERS

Ejecutar con:  python manage.py test cuentas
"""
from datetime import timedelta

from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import path, reverse
from django.utils import timezone

from auditoria.models import RegistroAuditoria
from configuracion.models import ConfiguracionNegocio

from . import roles
from .models import Usuario
from .permisos import rol_requerido

PASSWORD = "ClaveSegura2026"


#vistas de prueba para revisar los permisos por rol
@rol_requerido(roles.ADMINISTRADOR)
def solo_admin(request):
    from django.http import HttpResponse
    return HttpResponse("ok")


@rol_requerido(roles.ADMINISTRADOR, ocultar=True)
def secreta(request):
    from django.http import HttpResponse
    return HttpResponse("ok")


urlpatterns_prueba = [
    path("prueba/admin/", solo_admin),
    path("prueba/secreta/", secreta),
]


def crear_usuario(nombre, rol):
    usuario = Usuario.objects.create_user(nombre, password=PASSWORD)
    grupo, _ = Group.objects.get_or_create(name=rol)
    usuario.groups.add(grupo)
    return usuario


class InicioSesionTests(TestCase):
    def setUp(self):
        self.cajero = crear_usuario("cajero", roles.CAJERO)

    def test_cp_aut_01_credenciales_validas(self):
        r = self.client.post(reverse("login"), {"username": "cajero", "password": PASSWORD})
        self.assertRedirects(r, reverse("inicio"), fetch_redirect_response=False)
        self.assertTrue(RegistroAuditoria.objects.filter(accion=RegistroAuditoria.LOGIN_OK).exists())

    def test_cp_aut_01_credenciales_invalidas_mensaje_generico(self):
        r = self.client.post(reverse("login"), {"username": "cajero", "password": "mala"})
        self.assertContains(r, "Usuario o contraseña incorrectos.")
        r = self.client.post(reverse("login"), {"username": "noexiste", "password": "mala"})
        self.assertContains(r, "Usuario o contraseña incorrectos.")

    def test_cp_aut_02_cerrar_sesion(self):
        self.client.login(username="cajero", password=PASSWORD)
        self.client.post(reverse("logout"))
        r = self.client.get(reverse("inicio"))
        self.assertRedirects(r, f"{reverse('login')}?next=/")

    def test_cp_aut_04_bloqueo_tras_5_intentos(self):
        for _ in range(5):
            self.client.post(reverse("login"), {"username": "cajero", "password": "mala"})
        self.cajero.refresh_from_db()
        self.assertTrue(self.cajero.esta_bloqueado)
        # El sexto intento se rechaza aunque la contraseña sea correcta
        r = self.client.post(reverse("login"), {"username": "cajero", "password": PASSWORD})
        self.assertContains(r, "bloqueada")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_cp_aut_04_bloqueo_expira(self):
        self.cajero.bloqueado_hasta = timezone.now() - timedelta(minutes=1)
        self.cajero.save()
        r = self.client.post(reverse("login"), {"username": "cajero", "password": PASSWORD})
        self.assertRedirects(r, reverse("inicio"), fetch_redirect_response=False)

    def test_usuario_inactivo_no_entra(self):
        self.cajero.is_active = False
        self.cajero.save()
        r = self.client.post(reverse("login"), {"username": "cajero", "password": PASSWORD})
        self.assertContains(r, "Usuario o contraseña incorrectos.")


class PermisosTests(TestCase):

    def setUp(self):
        ConfiguracionNegocio(nombre_comercial="Tienda de prueba").save()
        self.admin = crear_usuario("admin", roles.ADMINISTRADOR)
        self.cajero = crear_usuario("cajero", roles.CAJERO)

    def test_cp_aut_03_cajero_recibe_403(self):
        with self.settings(ROOT_URLCONF=__name__):
            self.client.login(username="cajero", password=PASSWORD)
            self.assertEqual(self.client.get("/prueba/admin/").status_code, 403)

    def test_cp_aut_03_admin_si_entra(self):
        with self.settings(ROOT_URLCONF=__name__):
            self.client.login(username="admin", password=PASSWORD)
            self.assertEqual(self.client.get("/prueba/admin/").status_code, 200)

    def test_pagina_oculta_responde_404(self):
        with self.settings(ROOT_URLCONF=__name__):
            self.client.login(username="cajero", password=PASSWORD)
            self.assertEqual(self.client.get("/prueba/secreta/").status_code, 404)


class CambioPasswordTests(TestCase):
    def setUp(self):
        self.cajero = crear_usuario("cajero", roles.CAJERO)
        self.client.login(username="cajero", password=PASSWORD)

    def test_cp_aut_06_cambiar_propia_contrasena(self):
        nueva = "OtraClave2026x"
        r = self.client.post(reverse("cuentas:cambiar_password"), {
            "old_password": PASSWORD,
            "new_password1": nueva,
            "new_password2": nueva,
        })
        self.assertRedirects(r, reverse("inicio"), fetch_redirect_response=False)
        self.client.logout()
        self.assertFalse(self.client.login(username="cajero", password=PASSWORD))
        self.assertTrue(self.client.login(username="cajero", password=nueva))

    def test_contrasena_corta_rechazada(self):
        r = self.client.post(reverse("cuentas:cambiar_password"), {
            "old_password": PASSWORD,
            "new_password1": "abc12",
            "new_password2": "abc12",
        })
        self.assertEqual(r.status_code, 200)
        self.assertTrue(self.client.login(username="cajero", password=PASSWORD))

    def test_cambio_obligatorio_redirige(self):
        self.cajero.debe_cambiar_password = True
        self.cajero.save()
        r = self.client.get(reverse("inicio"))
        self.assertRedirects(r, reverse("cuentas:cambiar_password"))


# Rutas que usa PermisosTests (ROOT_URLCONF apunta a este módulo): las del sistema + las de prueba
from config.urls import urlpatterns as rutas_sistema  # noqa: E402

urlpatterns = urlpatterns_prueba + rutas_sistema


class EmpleadosTests(TestCase):
    #Gestión de empleados (casos CP-USR de la ERS)

    def setUp(self):
        ConfiguracionNegocio(nombre_comercial="Abarrotes Don Pepe").save()
        self.admin = crear_usuario("admin", roles.ADMINISTRADOR)
        self.cajero = crear_usuario("cajero", roles.CAJERO)
        self.client.login(username="admin", password=PASSWORD)

    def alta(self, **cambios):
        datos = {
            "first_name": "Ana", "last_name": "López", "username": "ana", "email": "",
            "rol": roles.CAJERO, "password1": "Mazatlan2026", "password2": "Mazatlan2026",
        }
        datos.update(cambios)
        return self.client.post(reverse("cuentas:nuevo"), datos)

    def editar(self, usuario, **cambios):
        datos = {"first_name": usuario.first_name or "X", "last_name": usuario.last_name, "email": usuario.email, "rol": usuario.rol}
        datos.update(cambios)
        return self.client.post(reverse("cuentas:editar", args=[usuario.pk]), datos)

    # ---------------------------------------------------------- Permisos

    def test_solo_el_administrador_entra(self):
        self.assertEqual(self.client.get(reverse("cuentas:usuarios")).status_code, 200)
        crear_usuario("encargado", roles.ENCARGADO)
        self.client.login(username="encargado", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("cuentas:usuarios")).status_code, 403)
        self.assertEqual(self.alta().status_code, 403)
        self.assertFalse(Usuario.objects.filter(username="ana").exists())

    # ---------------------------------------------------------- Alta

    def test_cp_usr_01_alta_con_rol_y_contrasena_temporal(self):
        r = self.alta()
        self.assertRedirects(r, reverse("cuentas:usuarios"))
        ana = Usuario.objects.get(username="ana")
        self.assertEqual(ana.rol, roles.CAJERO)
        self.assertTrue(ana.debe_cambiar_password)
        self.assertTrue(ana.check_password("Mazatlan2026"))
        self.assertTrue(RegistroAuditoria.objects.filter(accion=RegistroAuditoria.USUARIO_ALTA).exists())

    def test_alta_usuario_repetido(self):
        r = self.alta(username="CAJERO")
        self.assertContains(r, "Ya existe un empleado con ese nombre de usuario")

    def test_alta_contrasena_debil_o_distinta(self):
        self.assertContains(self.alta(password1="12345678", password2="12345678"), "text-danger")
        self.assertContains(self.alta(password2="otra-cosa-2026"), "Las contraseñas no coinciden")
        self.assertFalse(Usuario.objects.filter(username="ana").exists())

    def test_nuevo_empleado_debe_cambiar_contrasena_al_entrar(self):
        self.alta()
        self.client.logout()
        self.client.login(username="ana", password="Mazatlan2026")
        self.assertRedirects(self.client.get(reverse("ventas:caja")), reverse("cuentas:cambiar_password"))

    # ---------------------------------------------------------- Edición

    def test_cp_usr_03_cambiar_rol(self):
        self.editar(self.cajero, rol=roles.ENCARGADO, first_name="Pedro")
        self.cajero.refresh_from_db()
        self.assertEqual(self.cajero.rol, roles.ENCARGADO)
        self.assertEqual(self.cajero.first_name, "Pedro")
        self.assertEqual(self.cajero.groups.count(), 1)  # un solo rol
        registro = RegistroAuditoria.objects.get(accion=RegistroAuditoria.USUARIO_EDICION)
        self.assertIn("Cajero", registro.valor_anterior)
        self.assertIn("Encargado", registro.valor_nuevo)

    def test_no_cambia_el_nombre_de_usuario(self):
        self.editar(self.cajero, username="otro")
        self.cajero.refresh_from_db()
        self.assertEqual(self.cajero.username, "cajero")

    def test_no_puede_cambiar_su_propio_rol(self):
        segundo = crear_usuario("admin2", roles.ADMINISTRADOR)
        r = self.editar(self.admin, rol=roles.CAJERO)
        self.assertContains(r, "No puedes cambiar tu propio rol")
        self.assertEqual(self.admin.rol, roles.ADMINISTRADOR)
        self.assertTrue(segundo.is_active)

    def test_siempre_queda_un_administrador(self):
        segundo = crear_usuario("admin2", roles.ADMINISTRADOR)
        #con dos administradores si se le puede quitar el rol a uno
        self.editar(segundo, rol=roles.ENCARGADO)
        self.assertEqual(segundo.rol, roles.ENCARGADO)
        #pero no al ultimo
        from .servicios import ErrorEmpleados, validar_queda_un_administrador
        with self.assertRaises(ErrorEmpleados):
            validar_queda_un_administrador(self.admin, desactivar=True)

    # ---------------------------------------------------------- Activar / desactivar

    def test_cp_usr_04_desactivar_y_reactivar(self):
        self.client.post(reverse("cuentas:estado", args=[self.cajero.pk]))
        self.cajero.refresh_from_db()
        self.assertFalse(self.cajero.is_active)
        self.assertTrue(Usuario.objects.filter(pk=self.cajero.pk).exists())  # nunca se borra
        self.assertFalse(self.client.login(username="cajero", password=PASSWORD))
        self.client.login(username="admin", password=PASSWORD)
        self.client.post(reverse("cuentas:estado", args=[self.cajero.pk]))
        self.cajero.refresh_from_db()
        self.assertTrue(self.cajero.is_active)
        self.assertEqual(RegistroAuditoria.objects.filter(accion=RegistroAuditoria.USUARIO_ESTADO).count(), 2)

    def test_desactivado_pierde_su_sesion(self):
        otro = self.client_class()
        otro.login(username="cajero", password=PASSWORD)
        self.client.post(reverse("cuentas:estado", args=[self.cajero.pk]))
        self.assertRedirects(otro.get(reverse("ventas:caja")), reverse("login") + "?next=" + reverse("ventas:caja"))

    def test_no_se_desactiva_a_si_mismo(self):
        self.client.post(reverse("cuentas:estado", args=[self.admin.pk]))
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    # ---------------------------------------------------------- Contraseña y bloqueo

    def test_cp_usr_05_restablecer_contrasena(self):
        self.cajero.bloqueado_hasta = timezone.now() + timedelta(minutes=10)
        self.cajero.save()
        self.client.post(reverse("cuentas:password", args=[self.cajero.pk]), {
            "new_password1": "Temporal-2026", "new_password2": "Temporal-2026",
        })
        self.cajero.refresh_from_db()
        self.assertTrue(self.cajero.check_password("Temporal-2026"))
        self.assertTrue(self.cajero.debe_cambiar_password)
        self.assertIsNone(self.cajero.bloqueado_hasta)
        registro = RegistroAuditoria.objects.get(accion=RegistroAuditoria.USUARIO_PASSWORD)
        self.assertNotIn("Temporal-2026", registro.valor_nuevo)  # la contraseña nunca se guarda en la bitacora

    def test_restablecer_contrasena_invalida(self):
        self.client.post(reverse("cuentas:password", args=[self.cajero.pk]), {
            "new_password1": "123", "new_password2": "123",
        })
        self.cajero.refresh_from_db()
        self.assertTrue(self.cajero.check_password(PASSWORD))
        self.assertFalse(self.cajero.debe_cambiar_password)

    def test_desbloquear(self):
        self.cajero.bloqueado_hasta = timezone.now() + timedelta(minutes=10)
        self.cajero.save()
        self.assertContains(self.client.get(reverse("cuentas:editar", args=[self.cajero.pk])), "Desbloquear ahora")
        self.client.post(reverse("cuentas:desbloquear", args=[self.cajero.pk]))
        self.cajero.refresh_from_db()
        self.assertFalse(self.cajero.esta_bloqueado)

    def test_lista_y_filtros(self):
        r = self.client.get(reverse("cuentas:usuarios"), {"rol": roles.CAJERO})
        self.assertEqual(list(r.context["empleados"]), [self.cajero])
        self.cajero.is_active = False
        self.cajero.save()
        r = self.client.get(reverse("cuentas:usuarios"))
        self.assertNotIn(self.cajero, r.context["empleados"])
        r = self.client.get(reverse("cuentas:usuarios"), {"estado": "inactivos"})
        self.assertEqual(list(r.context["empleados"]), [self.cajero])
