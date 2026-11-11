from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

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
