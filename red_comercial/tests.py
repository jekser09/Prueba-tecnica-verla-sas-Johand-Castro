import json
import tempfile
from pathlib import Path

from datetime import date

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.http import HttpRequest, HttpResponse
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django_minify_html.middleware import MinifyHtmlMiddleware

from aliados.storage import MinifiedManifestStaticFilesStorage
from red_comercial.models import (
    AccionAuditoria,
    Aliado,
    AuditLog,
    Ciudad,
    ConcurrentModificationError,
    Coordinador,
    EstadoVendedor,
    Vendedor,
)


class StaticMinificationStorageTests(SimpleTestCase):
    """
    Pruebas unitarias para el pipeline de minificación y serialización MD5
    de archivos estáticos (MinifiedManifestStaticFilesStorage).
    """

    def test_post_process_minifies_js_and_css_and_creates_hashed_manifest(self):
        with tempfile.TemporaryDirectory() as tmp_source, tempfile.TemporaryDirectory() as tmp_static_root:
            source_storage = FileSystemStorage(location=tmp_source)
            target_storage = MinifiedManifestStaticFilesStorage(location=tmp_static_root)

            raw_js = (
                "// Comentario de prueba en JS\n"
                "function calcularCumplimiento ( meta , real ) {\n"
                "    /* Bloque de comentario */\n"
                "    return ( real / meta ) * 100;\n"
                "}\n"
            )
            raw_css = (
                "/* Comentario de tema oscuro VERLA */\n"
                ":root {\n"
                "    --verla-brand-indigo: #3B33BC ;\n"
                "    --verla-bg-canvas: #08071A ;\n"
                "}\n"
                ".card {\n"
                "    background-color: var(--verla-bg-canvas);\n"
                "    border: 1px solid #2A2768;\n"
                "}\n"
            )

            source_storage.save("js/app.js", ContentFile(raw_js.encode("utf-8")))
            source_storage.save("css/theme.css", ContentFile(raw_css.encode("utf-8")))
            target_storage.save("js/app.js", ContentFile(raw_js.encode("utf-8")))
            target_storage.save("css/theme.css", ContentFile(raw_css.encode("utf-8")))

            paths = {
                "js/app.js": (source_storage, "js/app.js"),
                "css/theme.css": (source_storage, "css/theme.css"),
            }

            results = list(target_storage.post_process(paths, dry_run=False))
            processed_map = {orig: (hashed, ok) for orig, hashed, ok in results}

            self.assertIn("js/app.js", processed_map)
            self.assertIn("css/theme.css", processed_map)

            hashed_js_name, js_ok = processed_map["js/app.js"]
            hashed_css_name, css_ok = processed_map["css/theme.css"]
            self.assertTrue(js_ok)
            self.assertTrue(css_ok)
            self.assertRegex(hashed_js_name, r"^js/app\.[0-9a-f]{12}\.js$")
            self.assertRegex(hashed_css_name, r"^css/theme\.[0-9a-f]{12}\.css$")

            # Verificar que el contenido tanto del archivo base como del archivo con hash esté minificado
            for js_file in ("js/app.js", hashed_js_name):
                with target_storage.open(js_file, "rb") as f:
                    js_content = f.read().decode("utf-8")
                self.assertNotIn("Comentario de prueba", js_content)
                self.assertNotIn("Bloque de comentario", js_content)
                self.assertIn("function calcularCumplimiento(meta,real){return(real/meta)*100;}", js_content)

            for css_file in ("css/theme.css", hashed_css_name):
                with target_storage.open(css_file, "rb") as f:
                    css_content = f.read().decode("utf-8")
                self.assertNotIn("Comentario de tema oscuro", css_content)
                self.assertIn(":root{--verla-brand-indigo:#3B33BC;--verla-bg-canvas:#08071A}", css_content)
                self.assertIn(".card{background-color:var(--verla-bg-canvas);border:1px solid #2A2768}", css_content)

            # Verificar que staticfiles.json exista y registre los nombres con hash MD5
            manifest_path = Path(tmp_static_root) / "staticfiles.json"
            self.assertTrue(manifest_path.exists())
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest_data["paths"]["js/app.js"], hashed_js_name)
            self.assertEqual(manifest_data["paths"]["css/theme.css"], hashed_css_name)


class HtmlMinificationMiddlewareTests(SimpleTestCase):
    """
    Pruebas unitarias para la minificación de respuestas HTML mediante MinifyHtmlMiddleware.
    """

    def test_middleware_minifies_html_response(self):
        unminified_html = (
            "<!DOCTYPE html>\n"
            "<html lang=\"es\" data-theme=\"dark\">\n"
            "    <head>\n"
            "        <!-- Comentario HTML que debe eliminarse -->\n"
            "        <title>  Portal VERLA SAS  </title>\n"
            "    </head>\n"
            "    <body>\n"
            "        <main class=\"container\">\n"
            "            <h1>Red Comercial</h1>\n"
            "        </main>\n"
            "    </body>\n"
            "</html>\n"
        )

        def get_response(_request: HttpRequest) -> HttpResponse:
            return HttpResponse(unminified_html, content_type="text/html; charset=utf-8")

        middleware = MinifyHtmlMiddleware(get_response)
        request = HttpRequest()
        response = middleware(request)
        body = response.content.decode("utf-8")

        self.assertNotIn("Comentario HTML que debe eliminarse", body)
        self.assertNotIn("\n        <main", body)
        self.assertIn("<main class=container><h1>Red Comercial</h1></main>", body)


class ModuleRoutingSmokeTests(TestCase):
    """
    Pruebas de integración para verificar las rutas base conectadas en aliados/urls.py.
    """

    def test_module_default_endpoints_respond_ok(self):
        # Los tres módulos requieren autenticación según sus guardas RBAC
        for protected_route in ("com_default", "op_default", "asis_default"):
            res = self.client.get(reverse(protected_route))
            self.assertEqual(res.status_code, 302)
            self.assertIn(reverse("login"), res.headers["Location"])


class RedComercialDomainModelTests(TestCase):
    """
    Pruebas unitarias para la jerarquía comercial (Ciudad, Aliado, Coordinador, Vendedor),
    control de concurrencia optimista (version) y bitácora de auditoría (AuditLog).
    """

    def setUp(self):
        User = get_user_model()
        self.actor = User.objects.create_user(username="auditor_verla", password="secret")
        self.bogota = Ciudad.objects.create(codigo="BOG", nombre="Bogotá D.C.", departamento="Cundinamarca")
        self.medellin = Ciudad.objects.create(codigo="MED", nombre="Medellín", departamento="Antioquia")
        self.cali = Ciudad.objects.create(codigo="CLO", nombre="Cali", departamento="Valle del Cauca")

        self.aliado_1 = Aliado.objects.create(
            nit="900111222-1",
            razon_social="Comercializadora Andina SAS",
            codigo_contrato="CTR-2026-001",
            correo_contacto="contacto@andina.co",
            telefono="3001112233",
        )
        self.aliado_2 = Aliado.objects.create(
            nit="900333444-2",
            razon_social="Distribución Pacífico SAS",
            codigo_contrato="CTR-2026-002",
            correo_contacto="contacto@pacifico.co",
            telefono="3003334455",
        )
        self.coordinador_1 = Coordinador.objects.create(
            aliado=self.aliado_1,
            documento="1010111222",
            nombre_completo="Carlos Ramírez",
            correo="cramirez@andina.co",
            telefono="3101112233",
        )
        self.coordinador_2 = Coordinador.objects.create(
            aliado=self.aliado_2,
            documento="1020333444",
            nombre_completo="Laura Gómez",
            correo="lgomez@pacifico.co",
            telefono="3103334455",
        )

    def test_vendedor_jerarquia_multiciudad_y_auditoria_creacion(self):
        vendedor = Vendedor.objects.create(
            coordinador=self.coordinador_1,
            documento="1030555666",
            nombre_completo="Andrés Pérez",
            correo="aperez@andina.co",
            telefono="3205556677",
            cargo="Ejecutivo Senior",
            ciudad_base=self.bogota,
            fecha_ingreso=date(2025, 2, 10),
        )
        vendedor.ciudades_operacion.set([self.bogota, self.medellin, self.cali])
        vendedor.registrar_creacion(usuario=self.actor)

        self.assertEqual(vendedor.version, 1)
        self.assertEqual(vendedor.ciudades_operacion.count(), 3)
        self.assertEqual(vendedor.aliado, self.aliado_1)
        self.assertTrue(vendedor.puede_operar)

        log = AuditLog.objects.filter(entidad="Vendedor", registro_id=vendedor.pk).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.accion, AccionAuditoria.CREACION)
        self.assertEqual(log.version_resultante, 1)
        self.assertEqual(log.usuario, self.actor)

    def test_vendedor_deriva_aliado_correctamente_de_coordinador(self):
        vendedor = Vendedor.objects.create(
            coordinador=self.coordinador_2,
            documento="1030999888",
            nombre_completo="Vendedor Pacífico",
            correo="pacifico@empresa.co",
            telefono="3209998888",
            ciudad_base=self.cali,
            fecha_ingreso=date(2025, 3, 1),
        )
        self.assertEqual(vendedor.aliado, self.aliado_2)
        self.assertEqual(vendedor.aliado.razon_social, "Distribución Pacífico SAS")

    def test_optimistic_update_incrementa_version_y_registra_diff_en_auditlog(self):
        self.aliado_1.registrar_creacion(usuario=self.actor)
        self.aliado_1.optimistic_update(
            expected_version=1,
            usuario=self.actor,
            telefono="3159990000",
            razon_social="Comercializadora Andina Renovada SAS",
        )
        self.assertEqual(self.aliado_1.version, 2)
        self.assertEqual(self.aliado_1.telefono, "3159990000")

        log = AuditLog.objects.filter(
            entidad="Aliado",
            registro_id=self.aliado_1.pk,
            accion=AccionAuditoria.ACTUALIZACION,
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.version_resultante, 2)
        self.assertEqual(
            log.cambios_json["telefono"],
            {"antes": "3001112233", "despues": "3159990000"},
        )

    def test_optimistic_update_lanza_excepcion_ante_version_desactualizada(self):
        # Primera actualización legítima sube versión de 1 -> 2
        self.aliado_1.optimistic_update(
            expected_version=1,
            usuario=self.actor,
            telefono="3110001111",
        )
        self.assertEqual(self.aliado_1.version, 2)

        # Intento concurrente con versión obsoleta (expected_version=1) debe fallar
        with self.assertRaises(ConcurrentModificationError):
            self.aliado_1.optimistic_update(
                expected_version=1,
                usuario=self.actor,
                telefono="3998887777",
            )

        self.aliado_1.refresh_from_db()
        self.assertEqual(self.aliado_1.version, 2)
        self.assertEqual(self.aliado_1.telefono, "3110001111")

    def test_cambiar_estado_vendedor_bloqueo_y_restriccion_operativa(self):
        vendedor = Vendedor.objects.create(
            coordinador=self.coordinador_1,
            documento="1040777888",
            nombre_completo="Marcela Torres",
            correo="mtorres@andina.co",
            telefono="3187778899",
            ciudad_base=self.medellin,
            fecha_ingreso=date(2025, 1, 15),
        )
        self.assertTrue(vendedor.puede_operar)

        vendedor.cambiar_estado(
            nuevo_estado=EstadoVendedor.BLOQUEADO,
            expected_version=1,
            usuario=self.actor,
            motivo="Incumplimiento de políticas de recaudo",
        )
        self.assertEqual(vendedor.version, 2)
        self.assertEqual(vendedor.estado, EstadoVendedor.BLOQUEADO)
        self.assertFalse(vendedor.puede_operar)

        log_bloqueo = AuditLog.objects.filter(
            entidad="Vendedor",
            registro_id=vendedor.pk,
            accion=AccionAuditoria.BLOQUEO,
        ).first()
        self.assertIsNotNone(log_bloqueo)
        self.assertEqual(log_bloqueo.cambios_json["estado"], {"antes": "ACTIVO", "despues": "BLOQUEADO"})

        vendedor.cambiar_estado(
            nuevo_estado=EstadoVendedor.INACTIVO,
            expected_version=2,
            usuario=self.actor,
            motivo="Licencia no remunerada",
        )
        self.assertEqual(vendedor.version, 3)
        self.assertFalse(vendedor.puede_operar)
        self.assertTrue(
            AuditLog.objects.filter(
                entidad="Vendedor",
                registro_id=vendedor.pk,
                accion=AccionAuditoria.CAMBIO_ESTADO,
            ).exists()
        )


class RateLimitMiddlewareTests(TestCase):
    """
    Pruebas automatizadas para el middleware de limitación de tasa (RateLimitMiddleware)
    en rutas generales y en el módulo de inteligencia artificial (/asistente/).
    """

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    @override_settings(
        RATE_LIMIT_ENABLED=True,
        RATE_LIMIT_WINDOW_SECONDS=60,
        RATE_LIMIT_GLOBAL_REQUESTS=5,
        RATE_LIMIT_AI_REQUESTS=2,
    )
    def test_solicitudes_dentro_del_limite_incluyen_cabeceras_ratelimit(self):
        url = reverse("portal_home")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-RateLimit-Limit"], "5")
        self.assertEqual(response["X-RateLimit-Remaining"], "4")

    @override_settings(
        RATE_LIMIT_ENABLED=True,
        RATE_LIMIT_WINDOW_SECONDS=60,
        RATE_LIMIT_GLOBAL_REQUESTS=3,
        RATE_LIMIT_AI_REQUESTS=2,
    )
    def test_exceder_limite_global_retorna_429_con_retry_after_y_mensaje_espanol(self):
        url = reverse("portal_home")
        for _ in range(3):
            ok_response = self.client.get(url)
            self.assertEqual(ok_response.status_code, 200)

        # Cuarta solicitud supera RATE_LIMIT_GLOBAL_REQUESTS=3 (con Accept JSON)
        blocked_json = self.client.get(url, HTTP_ACCEPT="application/json")
        self.assertEqual(blocked_json.status_code, 429)
        self.assertIn("Retry-After", blocked_json)
        self.assertEqual(blocked_json["X-RateLimit-Limit"], "3")
        self.assertEqual(blocked_json["X-RateLimit-Remaining"], "0")
        payload = blocked_json.json()
        self.assertIn("Demasiadas solicitudes", payload["error"])
        self.assertGreaterEqual(int(payload["retry_after"]), 1)

        # Solicitud HTML estándar también recibe 429 con mensaje en español
        blocked_html = self.client.get(url, HTTP_ACCEPT="text/html")
        self.assertEqual(blocked_html.status_code, 429)
        self.assertIn("Retry-After", blocked_html)
        self.assertIn("Demasiadas solicitudes", blocked_html.content.decode("utf-8"))

    @override_settings(
        RATE_LIMIT_ENABLED=True,
        RATE_LIMIT_WINDOW_SECONDS=60,
        RATE_LIMIT_GLOBAL_REQUESTS=10,
        RATE_LIMIT_AI_REQUESTS=2,
    )
    def test_modulo_asistente_ia_aplica_limite_estricto_independiente(self):
        ai_url = "/asistente/api/consultar/"
        r1 = self.client.get(ai_url)
        # La ruta /asistente/api/consultar/ responde 405 a GET pero consume presupuesto de tasa
        self.assertEqual(r1["X-RateLimit-Limit"], "2")
        self.assertEqual(r1["X-RateLimit-Remaining"], "1")

        r2 = self.client.get(ai_url)
        self.assertEqual(r2["X-RateLimit-Remaining"], "0")

        # Tercera solicitud a /asistente/ debe ser bloqueada con 429 JSON
        r3 = self.client.get(ai_url)
        self.assertEqual(r3.status_code, 429)
        self.assertEqual(r3["X-RateLimit-Limit"], "2")
        self.assertEqual(r3["X-RateLimit-Remaining"], "0")
        self.assertIn("Retry-After", r3)
        self.assertEqual(
            r3.json()["error"],
            "Demasiadas solicitudes. Por favor espere antes de intentar nuevamente.",
        )

        # Mientras tanto, las rutas generales siguen disponibles bajo su propio presupuesto
        general_response = self.client.get(reverse("portal_home"))
        self.assertEqual(general_response.status_code, 200)

    @override_settings(
        RATE_LIMIT_ENABLED=True,
        RATE_LIMIT_WINDOW_SECONDS=60,
        RATE_LIMIT_GLOBAL_REQUESTS=1,
        RATE_LIMIT_AI_REQUESTS=1,
    )
    async def test_modo_asgi_asincrono_y_exencion_de_rutas_estaticas(self):
        from aliados.ratelimit import RateLimitMiddleware

        async def dummy_async_view(_request: HttpRequest) -> HttpResponse:
            return HttpResponse("OK ASGI", status=200)

        middleware = RateLimitMiddleware(dummy_async_view)

        # Rutas /static/ y /media/ están exentas y no consumen cuota ni adjuntan cabeceras de límite
        for exempt_path in ("/static/css/app.css", "/media/ofertas/banner.png"):
            req = HttpRequest()
            req.path = exempt_path
            req.META["REMOTE_ADDR"] = "10.0.0.50"
            res = await middleware(req)
            self.assertEqual(res.status_code, 200)
            self.assertNotIn("X-RateLimit-Limit", res)

        # Primera solicitud asíncrona a /asistente/ pasa
        req1 = HttpRequest()
        req1.path = "/asistente/sugerir/"
        req1.META["REMOTE_ADDR"] = "10.0.0.50"
        res1 = await middleware(req1)
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1["X-RateLimit-Limit"], "1")
        self.assertEqual(res1["X-RateLimit-Remaining"], "0")

        # Segunda solicitud asíncrona a /asistente/ retorna 429 JSON
        req2 = HttpRequest()
        req2.path = "/asistente/sugerir/"
        req2.META["REMOTE_ADDR"] = "10.0.0.50"
        res2 = await middleware(req2)
        self.assertEqual(res2.status_code, 429)
        self.assertEqual(res2["X-RateLimit-Remaining"], "0")


class BaseThemeAndRBACTests(TestCase):
    """
    Pruebas de integración y unitarias para el diseño Dark Theme de VERLA SAS,
    las directivas de templates, simulador de roles y guardas RBAC / bloqueo operativo.
    """

    def setUp(self):
        self.user_model = get_user_model()
        self.ciudad = Ciudad.objects.create(
            codigo="MED",
            nombre="Medellín",
            departamento="Antioquia",
            activa=True,
        )
        self.aliado = Aliado.objects.create(
            nit="900999888-1",
            razon_social="Aliado Paisa SAS",
            codigo_contrato="CTR-PAISA-2026",
            correo_contacto="info@paisa.com",
            telefono="3001234567",
            activo=True,
        )
        self.coordinador = Coordinador.objects.create(
            aliado=self.aliado,
            documento="CC-COORD-MED",
            nombre_completo="Andrés Morales",
            correo="andres@paisa.com",
            telefono="3011112222",
            activo=True,
        )

    def test_home_page_renders_dark_theme_and_brand_assets(self):
        response = self.client.get(reverse("portal_home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-theme=dark')
        self.assertContains(response, 'verla.')
        self.assertContains(response, 'logo-verla.')
        self.assertContains(response, 'Simulador de Roles (Demo)')

    def test_login_page_renders_styled_form(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Iniciar Sesión')
        self.assertContains(response, 'name=username')
        self.assertContains(response, 'name=password')

    def test_simulador_roles_switches_session(self):
        # Simular cambio a Aliado
        res_aliado = self.client.post(
            reverse("simular_rol"),
            {"rol_simulado": "aliado", "next": reverse("portal_home")},
            follow=True,
        )
        self.assertEqual(res_aliado.status_code, 200)
        self.assertContains(res_aliado, "demo_aliado")
        self.assertContains(res_aliado, "ALIADO")

        # Simular cambio a Vendedor Activo
        res_vend_act = self.client.post(
            reverse("simular_rol"),
            {"rol_simulado": "vendedor_activo", "next": reverse("portal_home")},
            follow=True,
        )
        self.assertEqual(res_vend_act.status_code, 200)
        self.assertContains(res_vend_act, "VENDEDOR")
        self.assertContains(res_vend_act, "ACTIVO")

        # Simular cambio a Vendedor Bloqueado
        res_vend_bloq = self.client.post(
            reverse("simular_rol"),
            {"rol_simulado": "vendedor_bloqueado", "next": reverse("portal_home")},
            follow=True,
        )
        self.assertEqual(res_vend_bloq.status_code, 200)
        self.assertContains(res_vend_bloq, "BLOQUEADO")

    def test_guard_bloqueo_operativo_restricts_vendedor_bloqueado(self):
        from red_comercial.rbac import requerir_roles

        @requerir_roles("VENDEDOR", "ADMIN")
        def dummy_protected_view(request: HttpRequest) -> HttpResponse:
            return HttpResponse("OPERACION_PERMITIDA", status=200)

        # Usuario vendedor activo
        user_activo = self.user_model.objects.create_user("vend_ok", "ok@test.com", "pass123")
        vendedor_ok = Vendedor.objects.create(
            coordinador=self.coordinador,
            documento="CC-VEND-OK",
            nombre_completo="Vendedor Operativo",
            correo="ok@test.com",
            telefono="3000000000",
            cargo="Asesor",
            ciudad_base=self.ciudad,
            estado=EstadoVendedor.ACTIVO,
            fecha_ingreso=date(2026, 1, 1),
            usuario=user_activo,
        )

        req_ok = HttpRequest()
        req_ok.user = user_activo
        req_ok.path = "/operacion/mis-metas/"
        resp_ok = dummy_protected_view(req_ok)
        self.assertEqual(resp_ok.status_code, 200)
        self.assertEqual(resp_ok.content.decode(), "OPERACION_PERMITIDA")

        # Usuario vendedor bloqueado
        user_bloq = self.user_model.objects.create_user("vend_bloq", "bloq@test.com", "pass123")
        vendedor_bloq = Vendedor.objects.create(
            coordinador=self.coordinador,
            documento="CC-VEND-BLOQ",
            nombre_completo="Vendedor Sancionado",
            correo="bloq@test.com",
            telefono="3000000001",
            cargo="Asesor",
            ciudad_base=self.ciudad,
            estado=EstadoVendedor.BLOQUEADO,
            motivo_estado="Sanción disciplinaria vigente",
            fecha_ingreso=date(2026, 1, 1),
            usuario=user_bloq,
        )

        req_bloq = HttpRequest()
        req_bloq.user = user_bloq
        req_bloq.path = "/operacion/mis-metas/"
        resp_bloq = dummy_protected_view(req_bloq)
        self.assertEqual(resp_bloq.status_code, 403)
        self.assertIn("Acceso Comercial Bloqueado", resp_bloq.content.decode())
        self.assertIn("Sanción disciplinaria vigente", resp_bloq.content.decode())

    def test_coordinador_can_view_assigned_ally_and_cities_catalog(self):
        coord_user = self.user_model.objects.create_user("coord_user", "coord@test.com", "pass123")
        self.coordinador.usuario = coord_user
        self.coordinador.save()

        otro_aliado = Aliado.objects.create(
            nit="900111222-3",
            razon_social="Aliado Caribe SAS",
            codigo_contrato="CTR-CARIBE-2026",
            correo_contacto="info@caribe.com",
            telefono="3007654321",
            activo=True,
        )

        self.client.force_login(coord_user)

        # 1. Coordinador puede ver aliado_list (solo el aliado asignado, con botones de mutación deshabilitados)
        resp_aliado = self.client.get(reverse("aliado_list"))
        self.assertEqual(resp_aliado.status_code, 200)
        self.assertContains(resp_aliado, "Aliado Paisa SAS")
        self.assertNotContains(resp_aliado, "Aliado Caribe SAS")
        self.assertNotContains(resp_aliado, reverse("aliado_create"))
        self.assertContains(resp_aliado, "disabled")

        # 2. Coordinador puede ver ciudad_list (solo lectura, con botones de mutación deshabilitados)
        resp_ciudad = self.client.get(reverse("ciudad_list"))
        self.assertEqual(resp_ciudad.status_code, 200)
        self.assertContains(resp_ciudad, "Medellín")
        self.assertNotContains(resp_ciudad, reverse("ciudad_create"))
        self.assertContains(resp_ciudad, "disabled")

    def test_vendedor_home_page_renders_unified_card(self):
        vend_user = self.user_model.objects.create_user("vend_home", "home@test.com", "pass123")
        Vendedor.objects.create(
            coordinador=self.coordinador,
            documento="CC-VEND-HOME",
            nombre_completo="Vendedor Portal",
            correo="home@test.com",
            telefono="3000000002",
            cargo="Asesor",
            ciudad_base=self.ciudad,
            estado=EstadoVendedor.ACTIVO,
            fecha_ingreso=date(2026, 1, 1),
            usuario=vend_user,
        )

        self.client.force_login(vend_user)
        response = self.client.get(reverse("portal_home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mis Metas & Ofertas Comerciales")
        self.assertContains(response, "Ingresar a Mis Metas & Ofertas")
        self.assertNotContains(response, "Ofertas Vigentes")

    def test_aliado_can_view_vendedores_assigned_to_its_coordinators(self):
        aliado_user = self.user_model.objects.create_user("aliado_paisa_user", "aliado@paisa.com", "pass123")
        self.aliado.usuario = aliado_user
        self.aliado.save()

        # Vendedor de Aliado 1 (a través de self.coordinador)
        vendedor_paisa = Vendedor.objects.create(
            coordinador=self.coordinador,
            documento="CC-VEND-PAISA",
            nombre_completo="Vendedor Paisa",
            correo="paisa@test.com",
            telefono="3001112233",
            cargo="Asesor",
            ciudad_base=self.ciudad,
            estado=EstadoVendedor.ACTIVO,
            fecha_ingreso=date(2026, 1, 1),
        )

        # Aliado 2 ajeno con su propio coordinador y vendedor
        aliado_ajeno = Aliado.objects.create(
            nit="900555666-7",
            razon_social="Aliado Ajeno SAS",
            codigo_contrato="CTR-AJENO-2026",
            correo_contacto="info@ajeno.com",
            telefono="3009998877",
            activo=True,
        )
        coord_ajeno = Coordinador.objects.create(
            aliado=aliado_ajeno,
            documento="CC-COORD-AJENO",
            nombre_completo="Coordinador Ajeno",
            correo="coord@ajeno.com",
            telefono="3008887766",
            activo=True,
        )
        vendedor_ajeno = Vendedor.objects.create(
            coordinador=coord_ajeno,
            documento="CC-VEND-AJENO",
            nombre_completo="Vendedor Ajeno",
            correo="ajeno@test.com",
            telefono="3002223344",
            cargo="Asesor",
            ciudad_base=self.ciudad,
            estado=EstadoVendedor.ACTIVO,
            fecha_ingreso=date(2026, 1, 1),
        )

        self.client.force_login(aliado_user)
        response = self.client.get(reverse("vendedor_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Vendedor Paisa")
        self.assertContains(response, "CC-VEND-PAISA")
        self.assertNotContains(response, "Vendedor Ajeno")
        self.assertNotContains(response, "CC-VEND-AJENO")

    def test_unauthorized_action_redirects_to_referer_or_list_instead_of_home(self):
        aliado_user = self.user_model.objects.create_user("aliado_redir", "aliado@redir.com", "pass123")
        self.aliado.usuario = aliado_user
        self.aliado.save()

        vendedor = Vendedor.objects.create(
            coordinador=self.coordinador,
            documento="CC-VEND-REDIR",
            nombre_completo="Vendedor Redir",
            correo="redir@test.com",
            telefono="3001112233",
            cargo="Asesor",
            ciudad_base=self.ciudad,
            estado=EstadoVendedor.ACTIVO,
            fecha_ingreso=date(2026, 1, 1),
        )

        self.client.force_login(aliado_user)

        # 1. Con HTTP_REFERER regresa a la lista donde estaba y no al inicio
        resp_with_referer = self.client.get(
            reverse("vendedor_update", kwargs={"pk": vendedor.pk}),
            HTTP_REFERER=reverse("vendedor_list"),
        )
        self.assertRedirects(resp_with_referer, reverse("vendedor_list"))

        # 2. Sin HTTP_REFERER regresa a vendedor_list y NO a portal_home
        resp_without_referer = self.client.get(reverse("vendedor_update", kwargs={"pk": vendedor.pk}))
        self.assertRedirects(resp_without_referer, reverse("vendedor_list"))

        # 3. Solo cuando el rol no tiene acceso a la vista completa del módulo, redirige a su portal o inicio
        vend_user = self.user_model.objects.create_user("vend_unauth", "v@unauth.com", "pass123")
        Vendedor.objects.create(
            coordinador=self.coordinador,
            documento="CC-VEND-UNAUTH",
            nombre_completo="Vendedor Unauth",
            correo="v@unauth.com",
            telefono="3000000009",
            cargo="Asesor",
            ciudad_base=self.ciudad,
            estado=EstadoVendedor.ACTIVO,
            fecha_ingreso=date(2026, 1, 1),
            usuario=vend_user,
        )
        self.client.force_login(vend_user)
        resp_module = self.client.get(reverse("com_default"))
        self.assertRedirects(resp_module, reverse("op_default"))


class RedComercialCRUDAndConcurrencyViewTests(TestCase):
    """
    Pruebas de vistas CRUD, control de concurrencia optimista HTTP 409
    y auditoría para la Red Comercial.
    """

    def setUp(self):
        self.user_model = get_user_model()
        self.admin_user = self.user_model.objects.create_superuser("admin_crud", "admin@crud.com", "pass123")
        self.client.force_login(self.admin_user)

        self.ciudad_cali = Ciudad.objects.create(
            codigo="CLO",
            nombre="Cali",
            departamento="Valle del Cauca",
            activa=True,
        )
        self.ciudad_bogota = Ciudad.objects.create(
            codigo="BOG",
            nombre="Bogotá",
            departamento="Cundinamarca",
            activa=True,
        )
        self.aliado = Aliado.objects.create(
            nit="901000111-2",
            razon_social="Aliado del Valle SAS",
            codigo_contrato="CTR-VALLE-2026",
            correo_contacto="valle@aliado.com",
            telefono="3120001122",
            activo=True,
        )
        self.coordinador = Coordinador.objects.create(
            aliado=self.aliado,
            documento="CC-COORD-VALLE",
            nombre_completo="Elena Restrepo",
            correo="elena@valle.com",
            telefono="3159998877",
            activo=True,
        )

    def test_dashboard_red_comercial_renders_metrics(self):
        response = self.client.get(reverse("com_default"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Gobernanza de Red Comercial")
        self.assertContains(response, "Ciudades de Cobertura")
        self.assertContains(response, "Aliados Comerciales")

    def test_ciudad_crud_and_optimistic_conflict_409(self):
        # 1. Crear ciudad
        res_create = self.client.post(
            reverse("ciudad_create"),
            {
                "codigo": "BAQ",
                "nombre": "Barranquilla",
                "departamento": "Atlántico",
                "activa": True,
            },
            follow=True,
        )
        self.assertEqual(res_create.status_code, 200)
        ciudad_baq = Ciudad.objects.get(codigo="BAQ")
        self.assertEqual(ciudad_baq.version, 1)

        # 2. Actualización exitosa con versión correcta
        res_edit_ok = self.client.post(
            reverse("ciudad_update", args=[ciudad_baq.pk]),
            {
                "version": ciudad_baq.version,
                "codigo": "BAQ",
                "nombre": "Barranquilla D.E.",
                "departamento": "Atlántico",
                "activa": True,
            },
            follow=True,
        )
        self.assertEqual(res_edit_ok.status_code, 200)
        ciudad_baq.refresh_from_db()
        self.assertEqual(ciudad_baq.version, 2)
        self.assertEqual(ciudad_baq.nombre, "Barranquilla D.E.")

        # 3. Actualización concurrente con versión desactualizada (stale version 1 vs 2) -> HTTP 409
        res_conflict = self.client.post(
            reverse("ciudad_update", args=[ciudad_baq.pk]),
            {
                "version": 1,  # Versión vieja
                "codigo": "BAQ",
                "nombre": "Nombre Concurrente Pisado",
                "departamento": "Atlántico",
                "activa": True,
            },
        )
        self.assertEqual(res_conflict.status_code, 409)
        self.assertContains(res_conflict, "Conflicto de Concurrencia", status_code=409)

        # Verificar que el registro no fue pisado
        ciudad_baq.refresh_from_db()
        self.assertEqual(ciudad_baq.nombre, "Barranquilla D.E.")

    def test_vendedor_crud_multi_city_and_state_blocking_audit(self):
        # 1. Crear Vendedor
        res_create = self.client.post(
            reverse("vendedor_create"),
            {
                "aliado": self.aliado.pk,
                "coordinador": self.coordinador.pk,
                "documento": "CC-11223344",
                "nombre_completo": "Camilo Torres",
                "correo": "camilo@valle.com",
                "telefono": "3187654321",
                "cargo": "Asesor Senior",
                "ciudad_base": self.ciudad_cali.pk,
                "ciudades_operacion": [self.ciudad_cali.pk, self.ciudad_bogota.pk],
                "estado": EstadoVendedor.ACTIVO,
                "motivo_estado": "",
                "fecha_ingreso": "2026-02-01",
            },
            follow=True,
        )
        self.assertEqual(res_create.status_code, 200)
        vendedor = Vendedor.objects.get(documento="CC-11223344")
        self.assertEqual(vendedor.ciudades_operacion.count(), 2)

        # 2. Transición a BLOQUEADO
        res_bloqueo = self.client.post(
            reverse("vendedor_update", args=[vendedor.pk]),
            {
                "version": vendedor.version,
                "aliado": self.aliado.pk,
                "coordinador": self.coordinador.pk,
                "documento": "CC-11223344",
                "nombre_completo": "Camilo Torres",
                "correo": "camilo@valle.com",
                "telefono": "3187654321",
                "cargo": "Asesor Senior",
                "ciudad_base": self.ciudad_cali.pk,
                "ciudades_operacion": [self.ciudad_cali.pk],
                "estado": EstadoVendedor.BLOQUEADO,
                "motivo_estado": "Incumplimiento de entregas comerciales",
                "fecha_ingreso": "2026-02-01",
            },
            follow=True,
        )
        self.assertEqual(res_bloqueo.status_code, 200)
        vendedor.refresh_from_db()
        self.assertEqual(vendedor.estado, EstadoVendedor.BLOQUEADO)

        # Verificar que se registró la bitácora de auditoría con acción BLOQUEO
        log_bloqueo = AuditLog.objects.filter(entidad="Vendedor", registro_id=vendedor.pk).order_by("-fecha_evento").first()
        self.assertIsNotNone(log_bloqueo)
        self.assertEqual(log_bloqueo.accion, AccionAuditoria.BLOQUEO)
        self.assertEqual(log_bloqueo.cambios_json["estado"]["despues"], EstadoVendedor.BLOQUEADO)

    def test_vendedor_update_view_renders_fecha_ingreso_in_html5_format(self):
        vendedor = Vendedor.objects.create(
            coordinador=self.coordinador,
            documento="CC-DATE-TEST",
            nombre_completo="Vendedor Date Test",
            correo="date@test.com",
            telefono="3009990000",
            cargo="Asesor",
            ciudad_base=self.ciudad_cali,
            estado=EstadoVendedor.ACTIVO,
            fecha_ingreso=date(2026, 4, 15),
        )
        response = self.client.get(reverse("vendedor_update", args=[vendedor.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value=2026-04-15')

    def test_audit_log_list_view_renders_changes(self):
        # Provocar cambio para tener registros de auditoría
        self.ciudad_cali.optimistic_update(
            expected_version=self.ciudad_cali.version,
            usuario=self.admin_user,
            nombre="Santiago de Cali",
        )
        response = self.client.get(reverse("audit_log_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bitácora de Auditoría")
        self.assertContains(response, "Ciudad")

    def test_admin_delete_ciudad_success(self):
        ciudad_nueva = Ciudad.objects.create(codigo="PER", nombre="Pereira", departamento="Risaralda")
        res = self.client.post(reverse("ciudad_delete", args=[ciudad_nueva.pk]), follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(Ciudad.objects.filter(pk=ciudad_nueva.pk).exists())
        log = AuditLog.objects.filter(entidad="Ciudad", registro_id=ciudad_nueva.pk, accion=AccionAuditoria.ELIMINACION).first()
        self.assertIsNotNone(log)

    def test_admin_delete_ciudad_protected_error(self):
        # Crear vendedor asignado a self.ciudad_cali
        Vendedor.objects.create(
            coordinador=self.coordinador,
            documento="CC-TEST-CIUDAD-PROT",
            nombre_completo="Vendedor Ciudad Prot",
            correo="vendedor_prot@valle.com",
            telefono="3009998877",
            cargo="Asesor",
            ciudad_base=self.ciudad_cali,
            estado=EstadoVendedor.ACTIVO,
            fecha_ingreso=date(2026, 1, 1),
        )
        res = self.client.post(reverse("ciudad_delete", args=[self.ciudad_cali.pk]), follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(Ciudad.objects.filter(pk=self.ciudad_cali.pk).exists())
        self.assertContains(res, "No se puede eliminar la ciudad")

    def test_admin_delete_aliado_success_and_protected(self):
        # Aliado sin dependencias
        aliado_libre = Aliado.objects.create(
            nit="800999000-1",
            razon_social="Aliado Libre SAS",
            codigo_contrato="CTR-LIB-01",
            correo_contacto="libre@aliado.com",
            telefono="3000000000",
        )
        res = self.client.post(reverse("aliado_delete", args=[aliado_libre.pk]), follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(Aliado.objects.filter(pk=aliado_libre.pk).exists())
        self.assertTrue(AuditLog.objects.filter(entidad="Aliado", registro_id=aliado_libre.pk, accion=AccionAuditoria.ELIMINACION).exists())

        # self.aliado tiene a self.coordinador asociado -> ProtectedError
        res_prot = self.client.post(reverse("aliado_delete", args=[self.aliado.pk]), follow=True)
        self.assertEqual(res_prot.status_code, 200)
        self.assertTrue(Aliado.objects.filter(pk=self.aliado.pk).exists())
        self.assertContains(res_prot, "No se puede eliminar el aliado")

    def test_admin_delete_coordinador_success_and_protected(self):
        coord_libre = Coordinador.objects.create(
            aliado=self.aliado,
            documento="CC-998877",
            nombre_completo="Coordinador Sin Vendedores",
            correo="libre@coord.com",
            telefono="3119998877",
        )
        res = self.client.post(reverse("coordinador_delete", args=[coord_libre.pk]), follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(Coordinador.objects.filter(pk=coord_libre.pk).exists())
        self.assertTrue(AuditLog.objects.filter(entidad="Coordinador", registro_id=coord_libre.pk, accion=AccionAuditoria.ELIMINACION).exists())

        # self.coordinador supervisa a un vendedor -> ProtectedError
        Vendedor.objects.create(
            coordinador=self.coordinador,
            documento="CC-TEST-COORD-PROT",
            nombre_completo="Vendedor Coord Prot",
            correo="vendedor_coord@valle.com",
            telefono="3009998878",
            cargo="Asesor",
            ciudad_base=self.ciudad_cali,
            estado=EstadoVendedor.ACTIVO,
            fecha_ingreso=date(2026, 1, 1),
        )
        res_prot = self.client.post(reverse("coordinador_delete", args=[self.coordinador.pk]), follow=True)
        self.assertEqual(res_prot.status_code, 200)
        self.assertTrue(Coordinador.objects.filter(pk=self.coordinador.pk).exists())
        self.assertContains(res_prot, "No se puede eliminar el coordinador")

    def test_admin_delete_vendedor_success_and_audit(self):
        vendedor = Vendedor.objects.create(
            coordinador=self.coordinador,
            documento="CC-DEL-ADMIN",
            nombre_completo="Vendedor Para Borrar",
            correo="del@admin.com",
            telefono="3001112233",
            cargo="Asesor",
            ciudad_base=self.ciudad_cali,
            estado=EstadoVendedor.ACTIVO,
            fecha_ingreso=date(2026, 1, 1),
        )
        res = self.client.post(reverse("vendedor_delete", args=[vendedor.pk]), follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(Vendedor.objects.filter(pk=vendedor.pk).exists())
        log = AuditLog.objects.filter(entidad="Vendedor", registro_id=vendedor.pk, accion=AccionAuditoria.ELIMINACION).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.cambios_json["documento"], "CC-DEL-ADMIN")
        self.assertContains(res, "eliminado exitosamente")

    def test_coordinador_delete_own_vendedor_success(self):
        coord_user = self.user_model.objects.create_user("coord_user_del", "coord_del@valle.com", "pass123")
        self.coordinador.usuario = coord_user
        self.coordinador.save()

        vendedor = Vendedor.objects.create(
            coordinador=self.coordinador,
            documento="CC-DEL-OWN",
            nombre_completo="Vendedor Propio Coord",
            correo="own@coord.com",
            telefono="3001112234",
            cargo="Asesor",
            ciudad_base=self.ciudad_cali,
            estado=EstadoVendedor.ACTIVO,
            fecha_ingreso=date(2026, 1, 1),
        )

        self.client.force_login(coord_user)
        res = self.client.post(reverse("vendedor_delete", args=[vendedor.pk]), follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(Vendedor.objects.filter(pk=vendedor.pk).exists())
        self.assertTrue(AuditLog.objects.filter(entidad="Vendedor", registro_id=vendedor.pk, accion=AccionAuditoria.ELIMINACION).exists())

    def test_coordinador_delete_other_coordinador_vendedor_forbidden(self):
        coord_user = self.user_model.objects.create_user("coord_user_del2", "coord_del2@valle.com", "pass123")
        self.coordinador.usuario = coord_user
        self.coordinador.save()

        otro_coord = Coordinador.objects.create(
            aliado=self.aliado,
            documento="CC-OTRO-COORD",
            nombre_completo="Otro Coordinador",
            correo="otro@coord.com",
            telefono="3150009988",
        )
        vendedor_ajeno = Vendedor.objects.create(
            coordinador=otro_coord,
            documento="CC-DEL-AJENO",
            nombre_completo="Vendedor Ajeno",
            correo="ajeno@del.com",
            telefono="3009998811",
            cargo="Asesor",
            ciudad_base=self.ciudad_cali,
            estado=EstadoVendedor.ACTIVO,
            fecha_ingreso=date(2026, 1, 1),
        )

        self.client.force_login(coord_user)
        res = self.client.post(reverse("vendedor_delete", args=[vendedor_ajeno.pk]), follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(Vendedor.objects.filter(pk=vendedor_ajeno.pk).exists())
        self.assertContains(res, "No tiene autorización para eliminar vendedores de otra coordinación.")
        self.assertFalse(AuditLog.objects.filter(entidad="Vendedor", registro_id=vendedor_ajeno.pk, accion=AccionAuditoria.ELIMINACION).exists())

    def test_unauthorized_user_cannot_delete_vendedor(self):
        vendedor = Vendedor.objects.create(
            coordinador=self.coordinador,
            documento="CC-UNAUTH-DEL",
            nombre_completo="Vendedor Protegido",
            correo="unauth@del.com",
            telefono="3008887766",
            cargo="Asesor",
            ciudad_base=self.ciudad_cali,
            estado=EstadoVendedor.ACTIVO,
            fecha_ingreso=date(2026, 1, 1),
        )
        self.client.logout()

        res_anon = self.client.post(reverse("vendedor_delete", args=[vendedor.pk]))
        self.assertEqual(res_anon.status_code, 302)
        self.assertTrue(Vendedor.objects.filter(pk=vendedor.pk).exists())






