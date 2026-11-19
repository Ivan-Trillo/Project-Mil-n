from django import forms


class CancelarVentaForm(forms.Form):
    """RF-VEN-17: la cancelación siempre lleva un motivo"""

    motivo = forms.CharField(
        label="Motivo de la cancelación",
        max_length=200,
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 3,
            "placeholder": "Por ejemplo: el cliente devolvió el producto",
        }),
        error_messages={"required": "Escribe el motivo de la cancelación"},
    )

    def clean_motivo(self):
        motivo = self.cleaned_data["motivo"].strip()
        if not motivo:
            raise forms.ValidationError("Escribe el motivo de la cancelación")
        return motivo
