from datetime import timedelta
from decimal import Decimal
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from asistente_ia.models import AIAuditLog, CasoUsoIA, DecisionHumanaIA
from asistente_ia.services import (
    LIMITE_CONSULTAS_2MIN,
    LIMITE_CONSULTAS_DIA,
    verificar_cuota_usuario,
)
from operacion.models import MetaMensual, OfertaPeriodo
from red_comercial.models import Aliado, Ciudad, Coordinador, EstadoVendedor, Vendedor


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
            modelo="gemini-3.5-flash-lite",
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
    inyección de contexto, cuotas de tokens y registro human-in-the-loop.
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
        self.assertIn("texto_markdown", res["respuesta"])

    def test_api_consultar_asistente_returns_json_and_records_audit_log(self):
        response = self.client.post(
            reverse("asistente_api_consultar"),
            data=json.dumps({"mensaje": "Ayúdame con una oferta de internet", "current_path": "/operacion/"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertIn("log_id", data)
        self.assertIn("cuota", data)

        log = AIAuditLog.objects.get(pk=data["log_id"])
        self.assertEqual(log.usuario, self.user)
        self.assertEqual(log.caso_uso, CasoUsoIA.GENERACION_OFERTA)

    def test_api_veredicto_humano_updates_decision(self):
        log = AIAuditLog.objects.create(
            usuario=self.user,
            caso_uso=CasoUsoIA.GENERACION_OFERTA,
            modelo="gemini-3.5-flash-lite",
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

    def test_api_estado_retorna_rol_usuario_y_cuota(self):
        res = self.client.get(reverse("asistente_api_estado"))
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertIn("cuota", data)
        self.assertEqual(data["cuota"]["limite_dia"], LIMITE_CONSULTAS_DIA)
        self.assertEqual(data["cuota"]["limite_2min"], LIMITE_CONSULTAS_2MIN)
        self.assertIn("consultas disponibles hoy", data["mensaje_inicial"])

    def test_cuota_usuario_aplica_limite_2min_y_diario(self):
        # 1. Simular 15 consultas en los últimos 2 minutos que consumieron tokens de API real
        ahora = timezone.now()
        for i in range(LIMITE_CONSULTAS_2MIN):
            AIAuditLog.objects.create(
                usuario=self.user,
                caso_uso=CasoUsoIA.ANALISIS_METAS,
                modelo="gemini-3.8-flash",
                prompt_resumen=f"Consulta de prueba {i}",
                tokens_estimados=150,
                respuesta_json={},
            )

        cuota = verificar_cuota_usuario(self.user)
        self.assertFalse(cuota["puede_consultar"])
        self.assertIn("límite de 15 consultas cada 2 minutos", cuota["motivo_bloqueo"])

        # Intentar consultar vía API retorna HTTP 429
        res = self.client.post(
            reverse("asistente_api_consultar"),
            data=json.dumps({"mensaje": "¿Cómo van mis metas?", "current_path": "/"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 429)
        self.assertFalse(res.json()["ok"])
        self.assertIn("15 consultas cada 2 minutos", res.json()["error"])

    def test_cuota_usuario_aplica_limite_diario(self):
        # Simular 50 consultas hoy que consumieron tokens pero fuera de los 2 minutos
        tiempo_pasado = timezone.now() - timedelta(minutes=10)
        for i in range(LIMITE_CONSULTAS_DIA):
            log = AIAuditLog.objects.create(
                usuario=self.user,
                caso_uso=CasoUsoIA.GENERACION_OFERTA,
                modelo="gemini-3.8-flash",
                prompt_resumen=f"Consulta dia {i}",
                tokens_estimados=120,
                respuesta_json={},
            )
            AIAuditLog.objects.filter(pk=log.pk).update(creado_en=tiempo_pasado)

        cuota = verificar_cuota_usuario(self.user)
        self.assertFalse(cuota["puede_consultar"])
        self.assertIn("límite diario de 50 consultas", cuota["motivo_bloqueo"])

    def test_fallback_local_no_descuenta_cuota_de_tokens(self):
        # Consultas atendidas por contingencia local (tokens_estimados=0) no descuentan cuota
        for i in range(5):
            AIAuditLog.objects.create(
                usuario=self.user,
                caso_uso=CasoUsoIA.GENERACION_OFERTA,
                modelo="reglas-contingencia-v1",
                prompt_resumen="Consulta fallback",
                tokens_estimados=0,
                respuesta_json={},
            )

        cuota = verificar_cuota_usuario(self.user)
        self.assertTrue(cuota["puede_consultar"])
        self.assertEqual(cuota["consumidas_hoy"], 0)
        self.assertEqual(cuota["restantes_hoy"], LIMITE_CONSULTAS_DIA)

    def test_asistente_responde_vendedor_bloqueado_a_admin(self):
        ciudad = Ciudad.objects.create(codigo="BOG_B", nombre="Bogotá Bloq", departamento="Cundinamarca")
        aliado = Aliado.objects.create(nit="888-1", razon_social="Aliado Bloq", codigo_contrato="CTR-B1", correo_contacto="b@t.com", telefono="123")
        coord = Coordinador.objects.create(aliado=aliado, documento="CC-CB1", nombre_completo="Coord Bloq", correo="cb@t.com", telefono="123")
        Vendedor.objects.create(
            coordinador=coord,
            documento="CC-V-BLOQ",
            nombre_completo="Pedro Restrepo Bloqueado",
            correo="pedro@bloq.com",
            telefono="123",
            ciudad_base=ciudad,
            estado=EstadoVendedor.BLOQUEADO,
            motivo_estado="Incumplimiento reiterado de entregas",
            fecha_ingreso=timezone.now().date(),
        )

        res = self.client.post(
            reverse("asistente_api_consultar"),
            data=json.dumps({"mensaje": "Hola, dime que vendedor esta bloqueado", "current_path": "/"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        texto_resp = data["respuesta"].get("texto_markdown", "") or str(data["respuesta"])
        self.assertIn("Pedro Restrepo Bloqueado", texto_resp)
        self.assertIn("Incumplimiento reiterado", texto_resp)

    def test_api_consultar_rechaza_mensajes_demasiado_largos(self):
        prompt_largo = "A" * 401
        res = self.client.post(
            reverse("asistente_api_consultar"),
            data=json.dumps({"mensaje": prompt_largo, "current_path": "/"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("excede el límite", res.json()["error"])

    async def test_aislamiento_contexto_vendedor_vs_coordinador(self):
        from asgiref.sync import sync_to_async
        from asistente_ia.views import _construir_contexto_pantalla

        User = get_user_model()

        def _crear_datos():
            ciudad = Ciudad.objects.create(codigo="BOG_T", nombre="Bogotá Test", departamento="Cundinamarca")
            aliado = Aliado.objects.create(nit="999-1", razon_social="Aliado Test", codigo_contrato="CTR-T1", correo_contacto="a@t.com", telefono="123")
            user_coord = User.objects.create_user(username="coord_user", password="123")
            coord = Coordinador.objects.create(aliado=aliado, documento="CC-C1", nombre_completo="Coordinador Test", correo="c@t.com", telefono="123", usuario=user_coord)
            user_vend = User.objects.create_user(username="vend_user", password="123")
            vend = Vendedor.objects.create(
                coordinador=coord,
                documento="CC-V1",
                nombre_completo="Vendedor Test",
                correo="v@t.com",
                telefono="123",
                ciudad_base=ciudad,
                fecha_ingreso=timezone.now().date(),
                usuario=user_vend,
            )
            periodo = timezone.now().strftime("%Y-%m")
            MetaMensual.objects.create(
                vendedor=vend,
                periodo=periodo,
                meta_valor=Decimal("10000000.00"),
                resultado_real=Decimal("8500000.00"),
                observaciones="Cierre de prueba",
            )
            return user_vend, user_coord

        u_vend, u_coord = await sync_to_async(_crear_datos)()

        # Contexto del vendedor debe tener sus metas personales y 85%
        ctx_vend = await _construir_contexto_pantalla("/", u_vend)
        self.assertIn("METAS PERSONALES", ctx_vend)
        self.assertIn("85.0%", ctx_vend)
        self.assertIn("Vendedor Test", ctx_vend)

        # Contexto del coordinador debe tener su equipo
        ctx_coord = await _construir_contexto_pantalla("/", u_coord)
        self.assertIn("METAS EQUIPO SUPERVISADO", ctx_coord)
        self.assertIn("Coordinador Test", ctx_coord)

    def test_seed_demo_data_command_executes_cleanly(self):
        from django.core.management import call_command
        from io import StringIO

        out = StringIO()
        call_command("seed_demo_data", stdout=out)
        output = out.getvalue()
        self.assertIn("Sembrado completo", output)
        self.assertIn("10 aliados", output)
        self.assertIn("10 vendedores", output)

    def test_despachador_variaciones_intencion_bloqueado_bloquiar(self):
        """Verifica que variaciones morfológicas como 'bloquiar' identifiquen correctamente al vendedor bloqueado."""
        ciudad = Ciudad.objects.create(codigo="MED_B", nombre="Medellín Test", departamento="Antioquia")
        aliado = Aliado.objects.create(nit="888-1", razon_social="Aliado Medellín", codigo_contrato="CTR-M1", correo_contacto="m@t.com", telefono="123")
        coord = Coordinador.objects.create(aliado=aliado, documento="CC-C2", nombre_completo="Coordinador Paisa", correo="cp@t.com", telefono="123")
        Vendedor.objects.create(
            coordinador=coord,
            documento="CC-BLOQ-99",
            nombre_completo="Carlos Andrés Bloqueado",
            correo="carlos@t.com",
            telefono="3001234567",
            ciudad_base=ciudad,
            fecha_ingreso=timezone.now().date(),
            estado=EstadoVendedor.BLOQUEADO,
            motivo_estado="Fraude en contratos comerciales",
        )

        res = self.client.post(
            reverse("asistente_api_consultar"),
            data=json.dumps({"mensaje": "acaban de bloquiar a alguien mas dime quien es", "current_path": "/red-comercial/vendedores/"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        texto = data["respuesta"].get("texto_markdown", "") or str(data["respuesta"])
        self.assertIn("Carlos Andrés Bloqueado", texto)
        self.assertIn("Fraude en contratos comerciales", texto)

    def test_despachador_distingue_inactivos_vs_bloqueados(self):
        """Verifica que consultas por 'inactivos' listen vendedores inactivos y no los confundan con bloqueados."""
        ciudad = Ciudad.objects.create(codigo="CALI_I", nombre="Cali Test", departamento="Valle")
        aliado = Aliado.objects.create(nit="777-1", razon_social="Aliado Cali", codigo_contrato="CTR-C1", correo_contacto="c@t.com", telefono="123")
        coord = Coordinador.objects.create(aliado=aliado, documento="CC-C3", nombre_completo="Coordinador Cali", correo="cc@t.com", telefono="123")
        Vendedor.objects.create(
            coordinador=coord,
            documento="CC-INACT-01",
            nombre_completo="Marcela Inactiva",
            correo="marcela@t.com",
            telefono="3009876543",
            ciudad_base=ciudad,
            fecha_ingreso=timezone.now().date(),
            estado=EstadoVendedor.INACTIVO,
            motivo_estado="Licencia de maternidad",
        )

        res = self.client.post(
            reverse("asistente_api_consultar"),
            data=json.dumps({"mensaje": "¿qué vendedores están inactivos?", "current_path": "/red-comercial/vendedores/"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        texto = data["respuesta"].get("texto_markdown", "") or str(data["respuesta"])
        self.assertIn("Marcela Inactiva", texto)
        self.assertIn("Licencia de maternidad", texto)
        self.assertIn("inactiv", texto.lower())

    def test_despachador_consulta_ofertas_vigentes(self):
        """Verifica que consultas de 'qué ofertas hay disponibles' retornen las ofertas activas en el sistema."""
        periodo = timezone.now().strftime("%Y-%m")
        oferta = OfertaPeriodo.objects.create(
            periodo=periodo,
            titulo="Super Promo Fibra 1 Giga VERLA",
            descripcion="1000 Megas simétricas con instalación gratuita.",
            fecha_inicio=timezone.now().date(),
            fecha_fin=timezone.now().date() + timedelta(days=30),
            activa=True,
        )

        res = self.client.post(
            reverse("asistente_api_consultar"),
            data=json.dumps({"mensaje": "¿qué ofertas hay disponibles?", "current_path": "/operacion/ofertas/"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        texto = data["respuesta"].get("texto_markdown", "") or str(data["respuesta"])
        self.assertIn("Super Promo Fibra 1 Giga VERLA", texto)
        self.assertIn("1000 Megas simétricas", texto)

    def test_despachador_consulta_metas_porcentaje_cumplimiento(self):
        """Verifica que consultas sobre cumplimiento de metas devuelvan el porcentaje y valores consolidados."""
        ciudad = Ciudad.objects.create(codigo="BOG_M", nombre="Bogotá Metas", departamento="Cundinamarca")
        aliado = Aliado.objects.create(nit="555-1", razon_social="Aliado Metas", codigo_contrato="CTR-M5", correo_contacto="m5@t.com", telefono="123")
        coord = Coordinador.objects.create(aliado=aliado, documento="CC-C5", nombre_completo="Coordinador Metas", correo="cm@t.com", telefono="123")
        vend = Vendedor.objects.create(
            coordinador=coord,
            documento="CC-VM-01",
            nombre_completo="Vendedor Estrella",
            correo="estrella@t.com",
            telefono="3000000001",
            ciudad_base=ciudad,
            fecha_ingreso=timezone.now().date(),
            estado=EstadoVendedor.ACTIVO,
        )
        periodo = timezone.now().strftime("%Y-%m")
        MetaMensual.objects.create(
            vendedor=vend,
            periodo=periodo,
            meta_valor=Decimal("20000000.00"),
            resultado_real=Decimal("15000000.00"),
            observaciones="Avance positivo",
        )

        res = self.client.post(
            reverse("asistente_api_consultar"),
            data=json.dumps({"mensaje": "¿cuánto porcentaje de cumplimiento tenemos?", "current_path": "/operacion/metas/"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        texto = data["respuesta"].get("texto_markdown", "") or str(data["respuesta"])
        self.assertIn("75", texto)
        self.assertTrue("15.000.000" in texto or "15,000,000" in texto or "15" in texto)

    def test_consulta_kpis_generales_y_desglose_vendedores(self):
        """Verifica que la consulta de KPIs comerciales devuelva métricas consolidadas y desglose por asesor."""
        from asistente_ia.services import ejecutar_consulta_metas

        ciudad = Ciudad.objects.create(codigo="CALI_K", nombre="Cali KPI", departamento="Valle")
        aliado = Aliado.objects.create(nit="444-1", razon_social="Aliado KPI", codigo_contrato="CTR-K1", correo_contacto="k@t.com", telefono="123")
        coord = Coordinador.objects.create(aliado=aliado, documento="CC-CK1", nombre_completo="Coord KPI", correo="ck@t.com", telefono="123")
        v1 = Vendedor.objects.create(
            coordinador=coord,
            documento="CC-VK1",
            nombre_completo="Asesor Cumplido",
            correo="c@t.com",
            telefono="111",
            ciudad_base=ciudad,
            fecha_ingreso=timezone.now().date(),
        )
        v2 = Vendedor.objects.create(
            coordinador=coord,
            documento="CC-VK2",
            nombre_completo="Asesor Rezagado",
            correo="r@t.com",
            telefono="222",
            ciudad_base=ciudad,
            fecha_ingreso=timezone.now().date(),
        )
        periodo = timezone.now().strftime("%Y-%m")
        MetaMensual.objects.create(vendedor=v1, periodo=periodo, meta_valor=Decimal("10000000.00"), resultado_real=Decimal("12000000.00"))
        MetaMensual.objects.create(vendedor=v2, periodo=periodo, meta_valor=Decimal("10000000.00"), resultado_real=Decimal("5000000.00"))

        res = ejecutar_consulta_metas(periodo=periodo)
        datos = res["datos"]
        self.assertEqual(datos["meta_total"], 20000000.00)
        self.assertEqual(datos["resultado_real_total"], 17000000.00)
        self.assertEqual(datos["porcentaje_cumplimiento"], 85.0)
        self.assertEqual(datos["vendedores_meta_cumplida"], 1)
        self.assertEqual(datos["vendedores_en_alerta"], 1)
        self.assertEqual(len(datos["detalle_vendedores"]), 2)
        self.assertIn("Desglose de Metas por Vendedor", res["texto_markdown"])

    def test_asistente_brinda_consejo_desempeno_comercial(self):
        """Verifica que al solicitar un consejo o recomendación comercial se responda con sugerencias estratégicas."""
        res = self.client.post(
            reverse("asistente_api_consultar"),
            data=json.dumps({"mensaje": "¿Qué consejo o estrategia recomiendas para mejorar el desempeño de los vendedores rezagados?", "current_path": "/operacion/metas/"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        texto = data["respuesta"].get("texto_markdown", "")
        self.assertTrue(len(texto) > 50)
