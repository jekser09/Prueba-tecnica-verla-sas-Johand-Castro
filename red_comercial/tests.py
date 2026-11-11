import json
import tempfile
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.http import HttpRequest, HttpResponse
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django_minify_html.middleware import MinifyHtmlMiddleware

from aliados.storage import MinifiedManifestStaticFilesStorage


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
        endpoints = [
            ("com_default", "modulo red 'comercial' conectado"),
            ("op_default", "modulo 'operacion' conectado"),
            ("asis_default", "modulo 'asistente ia' conectado"),
        ]
        for route_name, expected_message in endpoints:
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {"response": expected_message})
