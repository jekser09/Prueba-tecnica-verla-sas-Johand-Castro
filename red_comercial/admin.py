from django.contrib import admin

from red_comercial.models import Aliado, AuditLog, Ciudad, Coordinador, Vendedor


@admin.register(Ciudad)
class CiudadAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "departamento", "activa", "version")
    search_fields = ("codigo", "nombre", "departamento")
    list_filter = ("activa", "departamento")


@admin.register(Aliado)
class AliadoAdmin(admin.ModelAdmin):
    list_display = ("nit", "razon_social", "codigo_contrato", "correo_contacto", "activo", "version")
    search_fields = ("nit", "razon_social", "codigo_contrato")
    list_filter = ("activo",)


@admin.register(Coordinador)
class CoordinadorAdmin(admin.ModelAdmin):
    list_display = ("documento", "nombre_completo", "aliado", "correo", "activo", "version")
    search_fields = ("documento", "nombre_completo", "correo")
    list_filter = ("activo", "aliado")


@admin.register(Vendedor)
class VendedorAdmin(admin.ModelAdmin):
    list_display = (
        "documento",
        "nombre_completo",
        "coordinador",
        "ciudad_base",
        "estado",
        "version",
    )
    search_fields = ("documento", "nombre_completo", "correo")
    list_filter = ("estado", "coordinador__aliado", "ciudad_base")
    filter_horizontal = ("ciudades_operacion",)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("fecha_evento", "entidad", "registro_id", "accion", "usuario", "version_resultante")
    search_fields = ("entidad", "registro_id")
    list_filter = ("entidad", "accion")
    readonly_fields = (
        "entidad",
        "registro_id",
        "accion",
        "usuario",
        "cambios_json",
        "version_resultante",
        "fecha_evento",
    )
