import json

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


class AsistenteIAServiceAndApiTests(TestCase):
    """
    Pruebas asíncronas y de API para el servicio de Gemini, fallback de contingencia,
    inyección de contexto y registro human-in-the-loop.
    """

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="asesor_ia", password="password123")
        self.client.force_login(self.user)

    async def test_consultar_gemini_fallback_inteligente(self):
        from asistente_ia.services import consultar_gemini

        # Consulta que activa el generador inteligente de oferta
        res = await consultar_gemini("Redactar una oferta comercial de fibra")
        self.assertTrue(res["ok"])
        self.assertIn("titulo_sugerido", res["respuesta"])
        self.assertIn("descripcion_comercial", res["respuesta"])

    def test_api_consultar_asistente_returns_json_and_records_audit_log(self):
        from django.urls import reverse

        response = self.client.post(
            reverse("asistente_api_consultar"),
            data=json.dumps({"mensaje": "Ayúdame con una oferta de internet", "current_path": "/operacion/"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertIn("log_id", data)

        log = AIAuditLog.objects.get(pk=data["log_id"])
        self.assertEqual(log.usuario, self.user)
        self.assertEqual(log.caso_uso, CasoUsoIA.GENERACION_OFERTA)

    def test_api_veredicto_humano_updates_decision(self):
        from django.urls import reverse

        log = AIAuditLog.objects.create(
            usuario=self.user,
            caso_uso=CasoUsoIA.GENERACION_OFERTA,
            modelo="gemini-2.5-flash",
            prompt_resumen="Borrador de prueba",
            respuesta_json={"titulo": "Test"},
        )

        res = self.client.post(
            reverse("asistente_api_veredicto"),
            data=json.dumps({"log_id": log.id, "decision": DecisionHumanaIA.ACEPTADO}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        log.refresh_from_db()
        self.assertEqual(log.decision_humana, DecisionHumanaIA.ACEPTADO)

    def test_seed_demo_data_command_executes_cleanly(self):
        from django.core.management import call_command
        from io import StringIO

        out = StringIO()
        call_command("seed_demo_data", stdout=out)
        output = out.getvalue()
        self.assertIn("Sembrado completo", output)
        self.assertIn("10 aliados", output)
        self.assertIn("10 vendedores", output)

