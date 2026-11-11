from django.contrib import admin

from operacion.models import MetaMensual, OfertaPeriodo


@admin.register(MetaMensual)
class MetaMensualAdmin(admin.ModelAdmin):
    list_display = ("periodo", "vendedor", "meta_valor", "resultado_real", "version")
    search_fields = ("periodo", "vendedor__nombre_completo", "vendedor__documento")
    list_filter = ("periodo", "vendedor__aliado")


@admin.register(OfertaPeriodo)
class OfertaPeriodoAdmin(admin.ModelAdmin):
    list_display = ("titulo", "periodo", "fecha_inicio", "fecha_fin", "aliado", "activa", "version")
    search_fields = ("titulo", "descripcion", "periodo")
    list_filter = ("periodo", "activa", "aliado")
    filter_horizontal = ("ciudades",)
