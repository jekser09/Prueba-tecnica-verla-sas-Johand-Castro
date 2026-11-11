from django.contrib.auth import get_user_model
from django.test import TestCase

from asistente_ia.models import AIAuditLog, CasoUsoIA, DecisionHumanaIA


class AsistenteIADomainModelTests(TestCase):
    """
    Pruebas unitarias para el registro de auditoría y telemetría de IA (AIAuditLog).
    """

    def test_creacion_y_actualizacion_veredicto_humano_en_aiauditlog(self):
        User = get_user_model()
        usuario = User.objects.create_user(username="coord_ia", password="secret")

        registro = AIAuditLog.objects.create(
            usuario=usuario,
            caso_uso=CasoUsoIA.GENERACION_OFERTA,
            modelo="gemini-2.5-flash",
            prompt_resumen="Generar oferta comercial para plan fibra 900 Mbps en Bogotá",
            respuesta_json={
                "titulo_sugerido": "Conéctate a 900 Mbps con VERLA",
                "descripcion_sugerida": "Velocidad simétrica para hogares y pymes.",
            },
            latencia_ms=340,
            tokens_estimados=185,
        )
        self.assertEqual(registro.decision_humana, DecisionHumanaIA.PENDIENTE)

        registro.decision_humana = DecisionHumanaIA.ACEPTADO
        registro.save(update_fields=["decision_humana", "actualizado_en"])
        registro.refresh_from_db()
        self.assertEqual(registro.decision_humana, DecisionHumanaIA.ACEPTADO)
