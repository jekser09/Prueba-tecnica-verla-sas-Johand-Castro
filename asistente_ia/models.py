from __future__ import annotations

from django.conf import settings
from django.db import models


class CasoUsoIA(models.TextChoices):
    GENERACION_OFERTA = "GENERACION_OFERTA", "Redacción de oferta comercial"
    ANALISIS_METAS = "ANALISIS_METAS", "Análisis ejecutivo de brechas de metas"


class DecisionHumanaIA(models.TextChoices):
    PENDIENTE = "PENDIENTE", "Pendiente de revisión"
    ACEPTADO = "ACEPTADO", "Aceptado sin cambios"
    EDITADO = "EDITADO", "Editado por usuario"
    DESCARTADO = "DESCARTADO", "Descartado"


class AIAuditLog(models.Model):
    """
    Registro de auditoría, telemetría y control humano (human-in-the-loop) para cada
    invocación al asistente de IA (Google Gemini).
    """

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Usuario solicitante",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="consultas_ia",
    )
    caso_uso = models.CharField(
        "Caso de uso",
        max_length=40,
        choices=CasoUsoIA.choices,
        db_index=True,
    )
    modelo = models.CharField("Modelo IA", max_length=60, default="gemini-3.5-flash-lite")
    prompt_resumen = models.TextField("Resumen del prompt enviado")
    respuesta_json = models.JSONField("Respuesta estructurada (JSON)", default=dict)
    latencia_ms = models.PositiveIntegerField("Latencia (ms)", default=0)
    tokens_estimados = models.PositiveIntegerField("Tokens estimados", default=0)
    decision_humana = models.CharField(
        "Decisión humana",
        max_length=20,
        choices=DecisionHumanaIA.choices,
        default=DecisionHumanaIA.PENDIENTE,
        db_index=True,
    )
    creado_en = models.DateTimeField("Creado en", auto_now_add=True, db_index=True)
    actualizado_en = models.DateTimeField("Actualizado en", auto_now=True)

    @property
    def respuesta_json_str(self) -> str:
        import json
        return json.dumps(self.respuesta_json or {}, ensure_ascii=False)

    class Meta:
        verbose_name = "Auditoría de IA"
        verbose_name_plural = "Auditorías de IA"
        ordering = ["-creado_en", "-id"]
        indexes = [
            models.Index(fields=["usuario", "creado_en"], name="idx_aiaudit_user_created"),
        ]

    def __str__(self) -> str:
        return f"{self.caso_uso} [{self.decision_humana}] ({self.latencia_ms} ms)"
