from django import forms

from .models import Categoria, MovimientoInventario, Producto, Proveedor


class FormularioBootstrap:
    """Agrega las clases de Bootstrap a todos los campos"""

    def aplicar_estilos(self):
        for campo in self.fields.values():
            widget = campo.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = "form-check-input"
            elif isinstance(widget, forms.Select):
                widget.attrs["class"] = "form-select"
            else:
                widget.attrs["class"] = "form-control"


class ProductoForm(FormularioBootstrap, forms.ModelForm):
    """
    RF-PRO-01 a RF-PRO-03 y RF-PRO-05

    La existencia solo se captura al dar de alta el producto, despues solo cambia
    con entradas, ajustes o ventas, para que siempre quede en el historial
    """

    class Meta:
        model = Producto
        fields = [
            "nombre",
            "codigo_barras",
            "sku",
            "categoria",
            "proveedor",
            "precio_venta",
            "costo",
            "existencia",
            "existencia_minima",
            "descripcion",
            "imagen",
        ]
        labels = {"existencia": "existencia inicial"}
        widgets = {
            "descripcion": forms.Textarea(attrs={"rows": 3}),
            "imagen": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        #solo categorias y proveedores activos 
        categoria_actual = self.instance.categoria_id if self.instance.pk else None
        proveedor_actual = self.instance.proveedor_id if self.instance.pk else None
        self.fields["categoria"].queryset = Categoria.objects.filter(activa=True) | Categoria.objects.filter(pk=categoria_actual)
        self.fields["proveedor"].queryset = Proveedor.objects.filter(activo=True) | Proveedor.objects.filter(pk=proveedor_actual)
        self.fields["categoria"].empty_label = "Sin categoría"
        self.fields["proveedor"].empty_label = "Sin proveedor"
        self.fields["precio_venta"].widget.attrs.update({"step": "0.01", "min": "0.01"})
        self.fields["costo"].widget.attrs.update({"step": "0.01", "min": "0"})
        self.fields["existencia"].widget.attrs["min"] = "0"
        self.fields["existencia_minima"].widget.attrs["min"] = "0"
        self.fields["codigo_barras"].help_text = "Escanéalo con el lector o escríbelo, déjalo vacío si el producto no tiene"
        self.fields["precio_venta"].help_text = "Con IVA incluido."
        if self.instance.pk:
            del self.fields["existencia"]
        self.aplicar_estilos()

    def clean_codigo_barras(self):
        #Vacio se guarda como NULL, asi varios productos pueden no tener código
        codigo = (self.cleaned_data.get("codigo_barras") or "").strip()
        return codigo or None

    def clean_sku(self):
        return self.cleaned_data["sku"].strip().upper()

    def clean_nombre(self):
        return self.cleaned_data["nombre"].strip()

    def clean_existencia(self):
        existencia = self.cleaned_data.get("existencia")
        if existencia is not None and existencia < 0:
            raise forms.ValidationError("La existencia no puede ser negativa")
        return existencia

    def clean_existencia_minima(self):
        minimo = self.cleaned_data.get("existencia_minima")
        if minimo is not None and minimo < 0:
            raise forms.ValidationError("La existencia mínima no puede ser negativa")
        return minimo


class MovimientoForm(FormularioBootstrap, forms.Form):
    """RF-PRO-08: entradas de mercancía y ajustes de inventario"""

    TIPOS = [
        (MovimientoInventario.ENTRADA, "Entrada de mercancia"),
        (MovimientoInventario.AJUSTE, "Ajuste (conteo físico, merma, robo…)"),
    ]
    tipo = forms.ChoiceField(label="Tipo de movimiento", choices=TIPOS)
    cantidad = forms.IntegerField(
        label="Cantidad",
        help_text="En un ajuste, usa negativo para restar (−3)",
    )
    motivo = forms.CharField(label="Motivo", max_length=200, required=False)

    def __init__(self, *args, producto=None, **kwargs):
        self.producto = producto
        super().__init__(*args, **kwargs)
        self.aplicar_estilos()

    def clean(self):
        datos = super().clean()
        tipo, cantidad = datos.get("tipo"), datos.get("cantidad")
        if cantidad is None:
            return datos
        if cantidad == 0:
            self.add_error("cantidad", "La cantidad no puede ser cero")
        elif tipo == MovimientoInventario.ENTRADA and cantidad < 0:
            self.add_error("cantidad", "Una entrada debe ser una cantidad positiva")
        elif self.producto and self.producto.existencia + cantidad < 0:
            self.add_error(
                "cantidad",
                f"No puedes restar {-cantidad}: solo hay {self.producto.existencia} en existencia",
            )
        if tipo == MovimientoInventario.AJUSTE and not datos.get("motivo", "").strip():
            self.add_error("motivo", "Indica el motivo del ajuste")
        return datos


class CategoriaForm(FormularioBootstrap, forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ["nombre"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_estilos()

    def clean_nombre(self):
        return self.cleaned_data["nombre"].strip()


class ProveedorForm(FormularioBootstrap, forms.ModelForm):
    class Meta:
        model = Proveedor
        fields = ["nombre", "contacto", "telefono", "correo", "rfc", "notas"]
        widgets = {"notas": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_estilos()

    def clean_rfc(self):
        return self.cleaned_data.get("rfc", "").strip().upper()
