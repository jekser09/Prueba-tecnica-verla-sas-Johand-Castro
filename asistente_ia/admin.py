from django.contrib import admin

from asistente_ia.models import AIAuditLog


@admin.register(AIAuditLog)
class AIAuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "creado_en",
        "caso_uso",
        "modelo",
        "usuario",
        "decision_humana",
        "latencia_ms",
        "tokens_estimados",
    )
    list_filter = ("caso_uso", "decision_humana", "modelo")
    search_fields = ("prompt_resumen",)
    readonly_fields = ("creado_en", "actualizado_en")
