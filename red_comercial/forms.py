from __future__ import annotations

from typing import Any

from django import forms

from red_comercial.models import Aliado, Ciudad, Coordinador, EstadoVendedor, Vendedor


class CiudadForm(forms.ModelForm):
    version = forms.IntegerField(widget=forms.HiddenInput(), required=False)

    class Meta:
        model = Ciudad
        fields = ["codigo", "nombre", "departamento", "activa"]
        widgets = {
            "codigo": forms.TextInput(attrs={"placeholder": "Ej: BOG"}),
            "nombre": forms.TextInput(attrs={"placeholder": "Ej: Bogotá D.C."}),
            "departamento": forms.TextInput(attrs={"placeholder": "Ej: Cundinamarca"}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["version"].initial = self.instance.version


class AliadoForm(forms.ModelForm):
    version = forms.IntegerField(widget=forms.HiddenInput(), required=False)

    class Meta:
        model = Aliado
        fields = [
            "nit",
            "razon_social",
            "codigo_contrato",
            "correo_contacto",
            "telefono",
            "activo",
        ]
        widgets = {
            "nit": forms.TextInput(attrs={"placeholder": "Ej: 900123456-1"}),
            "razon_social": forms.TextInput(attrs={"placeholder": "Razón social de la empresa"}),
            "codigo_contrato": forms.TextInput(attrs={"placeholder": "Ej: CTR-VERLA-2026"}),
            "correo_contacto": forms.EmailInput(attrs={"placeholder": "correo@aliado.com"}),
            "telefono": forms.TextInput(attrs={"placeholder": "Ej: 3001234567"}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["version"].initial = self.instance.version


class CoordinadorForm(forms.ModelForm):
    version = forms.IntegerField(widget=forms.HiddenInput(), required=False)

    class Meta:
        model = Coordinador
        fields = [
            "aliado",
            "documento",
            "nombre_completo",
            "correo",
            "telefono",
            "activo",
        ]
        widgets = {
            "documento": forms.TextInput(attrs={"placeholder": "Cédula de ciudadanía"}),
            "nombre_completo": forms.TextInput(attrs={"placeholder": "Nombre completo"}),
            "correo": forms.EmailInput(attrs={"placeholder": "correo@coordinador.com"}),
            "telefono": forms.TextInput(attrs={"placeholder": "Ej: 3101234567"}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["version"].initial = self.instance.version


class VendedorForm(forms.ModelForm):
    version = forms.IntegerField(widget=forms.HiddenInput(), required=False)

    class Meta:
        model = Vendedor
        fields = [
            "aliado",
            "coordinador",
            "documento",
            "nombre_completo",
            "correo",
            "telefono",
            "cargo",
            "ciudad_base",
            "ciudades_operacion",
            "estado",
            "motivo_estado",
            "fecha_ingreso",
        ]
        widgets = {
            "documento": forms.TextInput(attrs={"placeholder": "Cédula de ciudadanía"}),
            "nombre_completo": forms.TextInput(attrs={"placeholder": "Nombre completo"}),
            "correo": forms.EmailInput(attrs={"placeholder": "correo@vendedor.com"}),
            "telefono": forms.TextInput(attrs={"placeholder": "Ej: 3201234567"}),
            "cargo": forms.TextInput(attrs={"placeholder": "Ej: Asesor Comercial Senior"}),
            "motivo_estado": forms.TextInput(attrs={"placeholder": "Justificación si está inactivo o bloqueado"}),
            "fecha_ingreso": forms.DateInput(attrs={"type": "date"}),
            "ciudades_operacion": forms.SelectMultiple(attrs={"size": "4"}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["version"].initial = self.instance.version

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        aliado = cleaned_data.get("aliado")
        coordinador = cleaned_data.get("coordinador")
        estado = cleaned_data.get("estado")
        motivo = cleaned_data.get("motivo_estado")

        if aliado and coordinador and coordinador.aliado_id != aliado.id:
            self.add_error(
                "coordinador",
                f"El coordinador '{coordinador.nombre_completo}' no pertenece al aliado '{aliado.razon_social}'."
            )

        if estado in (EstadoVendedor.INACTIVO, EstadoVendedor.BLOQUEADO) and not motivo:
            self.add_error(
                "motivo_estado",
                f"Debe registrar un motivo para el estado {estado}."
            )

        return cleaned_data
