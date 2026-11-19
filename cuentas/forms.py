from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, SetPasswordForm
from django.contrib.auth.password_validation import validate_password

from auditoria.models import RegistroAuditoria
from auditoria.servicios import registrar

from . import roles
from .models import Usuario


class InicioSesionForm(AuthenticationForm):
    """
    RF-AUT-01: con datos invalidos se muestra un mensaje generico, sin decir si fallo el usuario o la contraseña
    RF-AUT-04: una cuenta bloqueada se rechaza aunque la contraseña sea correcta
    """

    error_messages = {
        "invalid_login": "Usuario o contraseña incorrectos.",
        "inactive": "Usuario o contraseña incorrectos.",
        "bloqueado": "La cuenta está bloqueada por varios intentos fallidos, intenta de nuevo en unos minutos",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Usuario"
        self.fields["password"].label = "Contraseña"
        self.fields["username"].widget.attrs.update(
            {"class": "form-control form-control-lg", "autofocus": True, "autocomplete": "username"}
        )
        self.fields["password"].widget.attrs.update(
            {"class": "form-control form-control-lg", "autocomplete": "current-password"}
        )

    def clean(self):
        nombre = self.cleaned_data.get("username")
        usuario = Usuario.objects.filter(username=nombre).first() if nombre else None
        if usuario is not None and usuario.esta_bloqueado:
            registrar(
                self.request,
                RegistroAuditoria.LOGIN_FALLIDO,
                elemento="Inicio de sesión",
                nuevo="Intento con la cuenta bloqueada",
                usuario=usuario,
                usuario_texto=nombre,
            )
            raise forms.ValidationError(self.error_messages["bloqueado"], code="bloqueado")
        return super().clean()


class CambiarPasswordForm(PasswordChangeForm):
    """RF-AUT-06: cambiar la propia contraseña pidiendo la actual."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].label = "Contraseña actual"
        self.fields["new_password1"].label = "Contraseña nueva"
        self.fields["new_password2"].label = "Confirma la contraseña nueva"
        self.fields["new_password1"].help_text = "Minimo 8 caracteres, que no sea comun ni solo numeros."
        for campo in self.fields.values():
            campo.widget.attrs["class"] = "form-control"


# ---------------------------------------------------------------- Empleados (RF-USR)

def _estilos_bootstrap(form):
    for campo in form.fields.values():
        if isinstance(campo.widget, forms.Select):
            campo.widget.attrs["class"] = "form-select"
        else:
            campo.widget.attrs["class"] = "form-control"


class EmpleadoForm(forms.ModelForm):
    #datos del empleado y su rol, el nombre de usuario no se cambia despues del alta

    rol = forms.ChoiceField(label="rol", choices=[(r, r) for r in roles.TODOS])

    class Meta:
        model = Usuario
        fields = ["username", "first_name", "last_name", "email"]
        labels = {
            "username": "nombre de usuario",
            "first_name": "nombre",
            "last_name": "apellidos",
            "email": "correo electrónico",
        }
        help_texts = {"username": "Con este nombre inicia sesión. Letras, números y . _ - sin espacios."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        if self.instance.pk:
            self.fields["username"].disabled = True
            self.fields["username"].help_text = "El nombre de usuario no se puede cambiar"
            self.fields["rol"].initial = self.instance.rol
        else:
            self.fields["rol"].initial = roles.CAJERO
        _estilos_bootstrap(self)
        self.fields["username"].widget.attrs["autocomplete"] = "off"

    def clean_username(self):
        nombre = self.cleaned_data["username"]
        if self.instance.pk:
            return self.instance.username
        if Usuario.objects.filter(username__iexact=nombre).exists():
            raise forms.ValidationError("Ya existe un empleado con ese nombre de usuario")
        return nombre


class EmpleadoNuevoForm(EmpleadoForm):
    #RF-USR-01: alta con una contraseña temporal que el empleado cambia al entrar

    password1 = forms.CharField(
        label="contraseña temporal",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="Mínimo 8 caracteres, El empleado la cambiará en su primer inicio de sesión",
    )
    password2 = forms.CharField(
        label="confirma la contraseña",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _estilos_bootstrap(self)

    def clean_password2(self):
        p1 = self.cleaned_data.get("password1")
        p2 = self.cleaned_data.get("password2")
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("Las contraseñas no coinciden")
        return p2

    def _post_clean(self):
        super()._post_clean()
        password = self.cleaned_data.get("password2")
        if password:
            try:
                validate_password(password, self.instance)
            except forms.ValidationError as error:
                self.add_error("password1", error)


class RestablecerPasswordForm(SetPasswordForm):
    #RF-USR-05: el Administrador pone una contraseña temporal

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_password1"].label = "contraseña temporal"
        self.fields["new_password2"].label = "confirma la contraseña"
        self.fields["new_password1"].help_text = "El empleado tendrá que cambiarla al iniciar sesión"
        self.fields["new_password2"].help_text = ""
        _estilos_bootstrap(self)
