import re

from django import forms

from .models import ConfiguracionNegocio

RFC_PATRON = re.compile(r"^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$")


class ConfiguracionNegocioForm(forms.ModelForm):
    class Meta:
        model = ConfiguracionNegocio
        fields = [
            "nombre_comercial",
            "razon_social",
            "rfc",
            "direccion",
            "telefono",
            "tasa_impuesto",
            "mensaje_ticket",
        ]
        widgets = {
            "direccion": forms.TextInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs["class"] = "form-control"
        self.fields["tasa_impuesto"].widget.attrs["step"] = "0.01"
        self.fields["rfc"].help_text = "12 caracteres para persona moral o 13 para persona física."

    def clean_rfc(self):
        rfc = self.cleaned_data.get("rfc", "").strip().upper()
        if rfc and not RFC_PATRON.match(rfc):
            raise forms.ValidationError("El RFC no tiene un formato válido. Revisa que esté completo.")
        return rfc

    def clean_nombre_comercial(self):
        return self.cleaned_data["nombre_comercial"].strip()
