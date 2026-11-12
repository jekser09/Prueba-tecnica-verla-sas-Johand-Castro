from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from operacion.models import MetaMensual, OfertaPeriodo
from red_comercial.models import Aliado, Ciudad, Coordinador, EstadoVendedor, Vendedor


class OperacionDomainModelTests(TestCase):
    """
    Pruebas unitarias para metas mensuales vs. resultados reales (MetaMensual)
    y ofertas vigentes por periodo con imágenes y reglas de visibilidad (OfertaPeriodo).
    """

    def setUp(self):
        self.bogota = Ciudad.objects.create(codigo="BOG", nombre="Bogotá D.C.", departamento="Cundinamarca")
        self.medellin = Ciudad.objects.create(codigo="MED", nombre="Medellín", departamento="Antioquia")
        self.cali = Ciudad.objects.create(codigo="CLO", nombre="Cali", departamento="Valle del Cauca")

        self.aliado_1 = Aliado.objects.create(
            nit="900111222-1",
            razon_social="Aliado Norte SAS",
            codigo_contrato="CTR-N-01",
            correo_contacto="norte@aliado.co",
            telefono="3001110000",
        )
        self.aliado_2 = Aliado.objects.create(
            nit="900222333-2",
            razon_social="Aliado Sur SAS",
            codigo_contrato="CTR-S-02",
            correo_contacto="sur@aliado.co",
            telefono="3002220000",
        )
        self.coord_1 = Coordinador.objects.create(
            aliado=self.aliado_1,
            documento="7001",
            nombre_completo="Coordinador Norte",
            correo="cnorte@aliado.co",
            telefono="3101110000",
        )
        self.coord_2 = Coordinador.objects.create(
            aliado=self.aliado_2,
            documento="7002",
            nombre_completo="Coordinador Sur",
            correo="csur@aliado.co",
            telefono="3102220000",
        )
        self.vendedor_1 = Vendedor.objects.create(
            aliado=self.aliado_1,
            coordinador=self.coord_1,
            documento="8001",
            nombre_completo="Vendedor Uno",
            correo="v1@aliado.co",
            telefono="3201110000",
            ciudad_base=self.bogota,
            fecha_ingreso=date(2025, 1, 10),
        )
        self.vendedor_1.ciudades_operacion.set([self.bogota, self.medellin])

        self.vendedor_2 = Vendedor.objects.create(
            aliado=self.aliado_1,
            coordinador=self.coord_1,
            documento="8002",
            nombre_completo="Vendedor Dos",
            correo="v2@aliado.co",
            telefono="3201110002",
            ciudad_base=self.medellin,
            fecha_ingreso=date(2025, 1, 12),
        )
        self.vendedor_3 = Vendedor.objects.create(
            aliado=self.aliado_2,
            coordinador=self.coord_2,
            documento="8003",
            nombre_completo="Vendedor Tres",
            correo="v3@aliado.co",
            telefono="3202220003",
            ciudad_base=self.cali,
            fecha_ingreso=date(2025, 2, 1),
        )

    def test_meta_mensual_calculo_brecha_cumplimiento_y_agregaciones(self):
        m1 = MetaMensual.objects.create(
            vendedor=self.vendedor_1,
            periodo="2026-03",
            meta_valor=Decimal("10000000.00"),
            resultado_real=Decimal("12500000.00"),
        )
        m2 = MetaMensual.objects.create(
            vendedor=self.vendedor_2,
            periodo="2026-03",
            meta_valor=Decimal("10000000.00"),
            resultado_real=Decimal("7500000.00"),
        )
        MetaMensual.objects.create(
            vendedor=self.vendedor_3,
            periodo="2026-03",
            meta_valor=Decimal("5000000.00"),
            resultado_real=Decimal("5000000.00"),
        )

        self.assertEqual(m1.brecha, Decimal("2500000.00"))
        self.assertEqual(m1.porcentaje_cumplimiento, Decimal("125.00"))
        self.assertEqual(m2.brecha, Decimal("-2500000.00"))
        self.assertEqual(m2.porcentaje_cumplimiento, Decimal("75.00"))

        resumen_coord = list(MetaMensual.resumen_por_coordinador("2026-03", aliado_id=self.aliado_1.pk))
        self.assertEqual(len(resumen_coord), 1)
        self.assertEqual(resumen_coord[0]["total_meta"], Decimal("20000000.00"))
        self.assertEqual(resumen_coord[0]["total_resultado"], Decimal("20000000.00"))

        resumen_aliado = list(MetaMensual.resumen_por_aliado("2026-03"))
        self.assertEqual(len(resumen_aliado), 2)

    def test_oferta_periodo_visibilidad_por_estado_aliado_ciudades_y_fechas(self):
        import shutil
        import tempfile
        from django.test import override_settings

        tmp_media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp_media, ignore_errors=True)
        with override_settings(MEDIA_ROOT=tmp_media):
            gif_1x1 = (
                b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!"
                b"\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
            )
            imagen_demo = SimpleUploadedFile("promo.gif", gif_1x1, content_type="image/gif")

            oferta_global = OfertaPeriodo.objects.create(
                titulo="Oferta Fibra Nacional",
                descripcion="50% de descuento primeros 3 meses",
                imagen=imagen_demo,
                periodo="2026-03",
                fecha_inicio=date(2026, 3, 1),
                fecha_fin=date(2026, 3, 31),
                activa=True,
            )
            oferta_medellin_aliado1 = OfertaPeriodo.objects.create(
                titulo="Bono Medellín Norte",
                descripcion="Bono exclusivo para operación en Medellín",
                periodo="2026-03",
                fecha_inicio=date(2026, 3, 1),
                fecha_fin=date(2026, 3, 31),
                activa=True,
                aliado=self.aliado_1,
            )
            oferta_medellin_aliado1.ciudades.add(self.medellin)

            oferta_cali_exclusiva = OfertaPeriodo.objects.create(
                titulo="Promo Cali",
                descripcion="Solo para Cali",
                periodo="2026-03",
                fecha_inicio=date(2026, 3, 1),
                fecha_fin=date(2026, 3, 31),
                activa=True,
            )
            oferta_cali_exclusiva.ciudades.add(self.cali)

            visibles_v1 = list(OfertaPeriodo.visibles_para_vendedor(self.vendedor_1, fecha=date(2026, 3, 15)))
            self.assertIn(oferta_global, visibles_v1)
            self.assertIn(oferta_medellin_aliado1, visibles_v1)
            self.assertNotIn(oferta_cali_exclusiva, visibles_v1)

            # Si el vendedor es BLOQUEADO, no puede visualizar ofertas operativas
            self.vendedor_1.cambiar_estado(
                nuevo_estado=EstadoVendedor.BLOQUEADO,
                expected_version=self.vendedor_1.version,
                motivo="Suspendido por auditoría",
            )
            self.assertEqual(OfertaPeriodo.visibles_para_vendedor(self.vendedor_1, fecha=date(2026, 3, 15)).count(), 0)

    def test_oferta_periodo_clean_rechaza_rango_fechas_invertido(self):
        oferta_invalida = OfertaPeriodo(
            titulo="Oferta Inválida",
            descripcion="Fechas invertidas",
            periodo="2026-03",
            fecha_inicio=date(2026, 3, 31),
            fecha_fin=date(2026, 3, 1),
        )
        with self.assertRaises(ValidationError):
            oferta_invalida.full_clean()


class OperacionViewsAndConcurrencyTests(TestCase):
    """
    Pruebas de integración para las vistas del dashboard de metas, agregaciones,
    portal del vendedor y control de concurrencia optimista HTTP 409.
    """

    def setUp(self):
        from django.contrib.auth import get_user_model
        from django.urls import reverse

        User = get_user_model()
        self.admin = User.objects.create_superuser("admin_op", "admin@op.com", "pass123")
        self.client.force_login(self.admin)

        self.ciudad = Ciudad.objects.create(codigo="CTG", nombre="Cartagena", departamento="Bolívar")
        self.aliado = Aliado.objects.create(
            nit="900555666-1",
            razon_social="Aliado Caribe SAS",
            codigo_contrato="CTR-CARIBE-01",
            correo_contacto="caribe@aliado.co",
            telefono="3005550000",
        )
        self.coord = Coordinador.objects.create(
            aliado=self.aliado,
            documento="CC-COORD-CARIBE",
            nombre_completo="Marcos Polo",
            correo="marcos@caribe.co",
            telefono="3105550000",
        )
        self.user_vendedor = User.objects.create_user("vendedor_caribe", "vendedor@caribe.co", "pass123")
        self.vendedor = Vendedor.objects.create(
            aliado=self.aliado,
            coordinador=self.coord,
            documento="CC-VEND-CARIBE",
            nombre_completo="Diana Arismendi",
            correo="diana@caribe.co",
            telefono="3205550000",
            cargo="Asesor Caribe",
            ciudad_base=self.ciudad,
            estado=EstadoVendedor.ACTIVO,
            fecha_ingreso=date(2026, 1, 1),
            usuario=self.user_vendedor,
        )

    def test_dashboard_operacion_renders_metrics_and_drilldown(self):
        from django.urls import reverse

        MetaMensual.objects.create(
            vendedor=self.vendedor,
            periodo="2026-03",
            meta_valor=Decimal("20000000.00"),
            resultado_real=Decimal("22000000.00"),
        )
        response = self.client.get(reverse("op_default") + "?periodo=2026-03")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Control Operacional de Metas & Ofertas")
        self.assertContains(response, "$20000000")
        self.assertContains(response, "$22000000")
        self.assertContains(response, "110")
        self.assertContains(response, "%")

    def test_meta_mensual_crud_and_optimistic_conflict_409(self):
        from django.urls import reverse

        # 1. Crear meta
        res_create = self.client.post(
            reverse("meta_create"),
            {
                "vendedor": self.vendedor.pk,
                "periodo": "2026-04",
                "meta_valor": "10000000.00",
                "resultado_real": "5000000.00",
                "observaciones": "Meta de apertura",
            },
            follow=True,
        )
        self.assertEqual(res_create.status_code, 200)
        meta = MetaMensual.objects.get(vendedor=self.vendedor, periodo="2026-04")
        self.assertEqual(meta.version, 1)

        # 2. Actualización concurrente con versión desactualizada -> HTTP 409
        # Primero simular un update legítimo que avanza la versión a 2
        meta.optimistic_update(
            expected_version=1,
            usuario=self.admin,
            resultado_real=Decimal("8000000.00"),
        )
        self.assertEqual(meta.version, 2)

        # Ahora el cliente envía version=1 (stale)
        res_conflict = self.client.post(
            reverse("meta_update", args=[meta.pk]),
            {
                "version": 1,
                "vendedor": self.vendedor.pk,
                "periodo": "2026-04",
                "meta_valor": "10000000.00",
                "resultado_real": "9999999.00",
                "observaciones": "Intento de pisar datos concurrentemente",
            },
        )
        self.assertEqual(res_conflict.status_code, 409)
        self.assertContains(res_conflict, "Conflicto de Concurrencia", status_code=409)

        # Verificar que el resultado en base de datos quedó protegido en 8000000.00
        meta.refresh_from_db()
        self.assertEqual(meta.resultado_real, Decimal("8000000.00"))

    def test_vendedor_autenticado_views_only_his_metas_and_scoped_offers(self):
        from django.urls import reverse

        # Login con el vendedor autenticado
        self.client.force_login(self.user_vendedor)

        meta = MetaMensual.objects.create(
            vendedor=self.vendedor,
            periodo="2026-03",
            meta_valor=Decimal("15000000.00"),
            resultado_real=Decimal("12000000.00"),
        )
        today = timezone.localdate()
        oferta = OfertaPeriodo.objects.create(
            titulo="Promo Caribe Fibra",
            descripcion="Descuento en Cartagena",
            periodo=today.strftime("%Y-%m"),
            fecha_inicio=today,
            fecha_fin=today,
            activa=True,
            aliado=self.aliado,
        )
        oferta.ciudades.add(self.ciudad)

        response = self.client.get(reverse("op_default") + f"?periodo={today.strftime('%Y-%m')}")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ficha Comercial: Diana Arismendi")
        self.assertContains(response, f"Mi Meta en {today.strftime('%Y-%m')}")
        self.assertContains(response, "Promo Caribe Fibra")

