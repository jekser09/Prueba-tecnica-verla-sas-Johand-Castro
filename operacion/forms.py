from __future__ import annotations

from typing import Any

from django import forms

from operacion.models import MetaMensual, OfertaPeriodo
from red_comercial.models import Aliado, EstadoVendedor, Vendedor


class MetaMensualForm(forms.ModelForm):
    version = forms.IntegerField(widget=forms.HiddenInput(), required=False)

    class Meta:
        model = MetaMensual
        fields = [
            "vendedor",
            "periodo",
            "meta_valor",
            "resultado_real",
            "observaciones",
        ]
        widgets = {
            "periodo": forms.TextInput(attrs={"placeholder": "YYYY-MM (ej: 2026-03)"}),
            "meta_valor": forms.NumberInput(attrs={"step": "0.01", "placeholder": "Ej: 15000000.00"}),
            "resultado_real": forms.NumberInput(attrs={"step": "0.01", "placeholder": "Ej: 12500000.00"}),
            "observaciones": forms.TextInput(attrs={"placeholder": "Comentarios u observaciones de periodo"}),
        }

    def __init__(self, *args: Any, user: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["version"].initial = self.instance.version

        # Filtrar el selector de vendedores según el rol del usuario autenticado
        if user and hasattr(user, "perfil_coordinador") and user.perfil_coordinador:
            self.fields["vendedor"].queryset = Vendedor.objects.filter(
                coordinador=user.perfil_coordinador,
                estado=EstadoVendedor.ACTIVO,
            )
        elif user and hasattr(user, "perfil_aliado") and user.perfil_aliado:
            self.fields["vendedor"].queryset = Vendedor.objects.filter(
                coordinador__aliado=user.perfil_aliado,
                estado=EstadoVendedor.ACTIVO,
            )
        else:
            self.fields["vendedor"].queryset = Vendedor.objects.filter(
                estado=EstadoVendedor.ACTIVO,
            )


class OfertaPeriodoForm(forms.ModelForm):
    version = forms.IntegerField(widget=forms.HiddenInput(), required=False)

    class Meta:
        model = OfertaPeriodo
        fields = [
            "titulo",
            "descripcion",
            "imagen",
            "periodo",
            "fecha_inicio",
            "fecha_fin",
            "activa",
            "aliado",
            "ciudades",
        ]
        widgets = {
            "titulo": forms.TextInput(attrs={"placeholder": "Ej: Bono Fibra Óptica 300MB"}),
            "descripcion": forms.Textarea(attrs={"rows": 4, "placeholder": "Condiciones comerciales, comisiones y vigencia..."}),
            "periodo": forms.TextInput(attrs={"placeholder": "YYYY-MM (ej: 2026-03)"}),
            "fecha_inicio": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "fecha_fin": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "ciudades": forms.SelectMultiple(attrs={"size": "4"}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["version"].initial = self.instance.version
