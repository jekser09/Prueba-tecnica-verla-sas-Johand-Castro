from datetime import date
from decimal import Decimal
import os
import re
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from operacion.models import MetaMensual, OfertaPeriodo, ruta_imagen_oferta
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
            coordinador=self.coord_1,
            documento="8002",
            nombre_completo="Vendedor Dos",
            correo="v2@aliado.co",
            telefono="3201110002",
            ciudad_base=self.medellin,
            fecha_ingreso=date(2025, 1, 12),
        )
        self.vendedor_3 = Vendedor.objects.create(
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

    def test_cancel_and_delete_oferta_views(self):
        from django.urls import reverse
        from red_comercial.models import AuditLog, AccionAuditoria

        self.client.force_login(self.admin)
        today = timezone.localdate()
        oferta = OfertaPeriodo.objects.create(
            titulo="Promo Testing Cancel",
            descripcion="Descuento temporal",
            periodo=today.strftime("%Y-%m"),
            fecha_inicio=today,
            fecha_fin=today,
            activa=True,
            aliado=self.aliado,
        )

        # 1. Cancelar (soft delete)
        res_cancel = self.client.post(
            reverse("oferta_cancel_delete", args=[oferta.pk]),
            {"action_type": "cancelar"},
            follow=True,
        )
        self.assertEqual(res_cancel.status_code, 200)
        oferta.refresh_from_db()
        self.assertFalse(oferta.activa)

        # 2. Eliminar (hard delete)
        res_del = self.client.post(
            reverse("oferta_cancel_delete", args=[oferta.pk]),
            {"action_type": "eliminar"},
            follow=True,
        )
        self.assertEqual(res_del.status_code, 200)
        self.assertFalse(OfertaPeriodo.objects.filter(pk=oferta.pk).exists())
        self.assertTrue(AuditLog.objects.filter(entidad="OfertaPeriodo", registro_id=oferta.pk, accion=AccionAuditoria.ELIMINACION).exists())


class OfertaPeriodoMediaLifecycleTests(TestCase):
    """
    Pruebas integrales de ciclo de vida de archivos multimedia e imágenes promocionales
    en el dominio de operacion (OfertaPeriodo):
    - Convención de nombres y rutas de auditoría (ruta_imagen_oferta)
    - Creación con SimpleUploadedFile y persistencia en disco
    - Actualización optimista con reemplazo de imagen, depuración física de versiones obsoletas y AuditLog
    - Eliminación física al cancelar/eliminar ofertas (señal post_delete y vista)
    - Protección y limpieza de temporales en conflictos de concurrencia (HTTP 409)
    """

    def setUp(self):
        self.tmp_media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp_media, ignore_errors=True)
        self.override = override_settings(MEDIA_ROOT=self.tmp_media)
        self.override.enable()
        self.addCleanup(self.override.disable)

        User = get_user_model()
        self.admin = User.objects.create_superuser("admin_media", "admin@media.co", "pass123")
        self.client.force_login(self.admin)

        self.ciudad = Ciudad.objects.create(codigo="MDE", nombre="Medellín", departamento="Antioquia")
        self.aliado = Aliado.objects.create(
            nit="900999888-1",
            razon_social="Aliado Media SAS",
            codigo_contrato="CTR-MEDIA-01",
            correo_contacto="contacto@aliadomedia.co",
            telefono="3009998888",
        )

        # 1x1 GIF válido para pruebas de ImageField
        self.gif_bytes = (
            b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!"
            b"\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
        )

    def test_ruta_imagen_oferta_naming_convention(self):
        """
        Verifica que ruta_imagen_oferta genera el formato de ruta de auditoría:
        ofertas/<año>/<mes>/audit_oferta_<id_o_nueva>_<periodo>_<timestamp>_<slug>.<ext>
        """
        # 1. Instancia no guardada (pk=None)
        oferta_nueva = OfertaPeriodo(periodo="2026-06")
        path_nueva = ruta_imagen_oferta(oferta_nueva, "Promo Flash Verano.PNG")
        self.assertTrue(path_nueva.startswith("ofertas/2026/06/audit_oferta_nueva_202606_"))
        self.assertTrue(path_nueva.endswith(".png"))
        self.assertIn("promo-flash-verano", path_nueva)
        pattern_nueva = r"^ofertas/2026/06/audit_oferta_nueva_202606_\d+_promo-flash-verano\.png$"
        self.assertRegex(path_nueva, pattern_nueva)

        # 2. Instancia con pk existente
        oferta_guardada = OfertaPeriodo(periodo="2026-07")
        oferta_guardada.pk = 77
        path_guardada = ruta_imagen_oferta(oferta_guardada, "Descuento_Especial.JPG")
        self.assertTrue(path_guardada.startswith("ofertas/2026/07/audit_oferta_77_202607_"))
        self.assertTrue(path_guardada.endswith(".jpg"))
        self.assertIn("descuento_especial", path_guardada)
        pattern_guardada = r"^ofertas/2026/07/audit_oferta_77_202607_\d+_descuento_especial\.jpg$"
        self.assertRegex(path_guardada, pattern_guardada)

        # 3. Fallback cuando el periodo está vacío o tiene formato no estándar
        oferta_sin_periodo = OfertaPeriodo(periodo="")
        path_sin_periodo = ruta_imagen_oferta(oferta_sin_periodo, "banner.gif")
        hoy = timezone.now()
        año_actual, mes_actual = hoy.strftime("%Y"), hoy.strftime("%m")
        self.assertTrue(path_sin_periodo.startswith(f"ofertas/{año_actual}/{mes_actual}/audit_oferta_nueva_general_"))
        self.assertTrue(path_sin_periodo.endswith(".gif"))

    def test_crear_oferta_con_imagen_guarda_archivo_fisico_y_auditoria(self):
        """
        Verifica que al crear una OfertaPeriodo con SimpleUploadedFile, el archivo
        se almacena físicamente en disco bajo la ruta trazable y se registra en AuditLog.
        """
        archivo_subido = SimpleUploadedFile("volante_apertura.gif", self.gif_bytes, content_type="image/gif")
        datos = {
            "titulo": "Campaña Apertura Fibra",
            "descripcion": "Instalación gratis para nuevos suscriptores",
            "periodo": "2026-05",
            "fecha_inicio": "2026-05-01",
            "fecha_fin": "2026-05-31",
            "activa": True,
            "aliado": self.aliado.pk,
            "ciudades": [self.ciudad.pk],
            "imagen": archivo_subido,
        }

        res = self.client.post(reverse("oferta_create"), datos, follow=True)
        self.assertEqual(res.status_code, 200)

        oferta = OfertaPeriodo.objects.get(titulo="Campaña Apertura Fibra")
        self.assertTrue(bool(oferta.imagen))
        self.assertRegex(oferta.imagen.name, r"^ofertas/2026/05/audit_oferta_nueva_202605_\d+_volante_apertura\.gif$")

        # Comprobar existencia física en el sistema de archivos del servidor
        self.assertTrue(default_storage.exists(oferta.imagen.name))
        self.assertTrue(os.path.exists(oferta.imagen.path))

        # Comprobar trazabilidad en AuditLog
        log_creacion = AuditLog.objects.get(
            entidad="OfertaPeriodo",
            registro_id=oferta.pk,
            accion=AccionAuditoria.CREACION,
        )
        self.assertEqual(log_creacion.cambios_json.get("imagen"), oferta.imagen.name)
        self.assertEqual(log_creacion.version_resultante, 1)

    def test_actualizar_oferta_optimistic_update_reemplaza_imagen_y_elimina_archivo_anterior(self):
        """
        Verifica que VersionedModel.optimistic_update al recibir un nuevo archivo:
        1. Guarda el nuevo archivo en almacenamiento.
        2. Elimina físicamente el archivo anterior del disco (sin dejar huérfanos).
        3. Actualiza la ruta relativa en la base de datos e incrementa version.
        4. Registra el diferencial antes/después en AuditLog.
        """
        archivo_v1 = SimpleUploadedFile("version_uno.gif", self.gif_bytes, content_type="image/gif")
        oferta = OfertaPeriodo.objects.create(
            titulo="Promo Aniversario",
            descripcion="Descuentos del 20%",
            periodo="2026-06",
            fecha_inicio=date(2026, 6, 1),
            fecha_fin=date(2026, 6, 30),
            activa=True,
            imagen=archivo_v1,
        )
        old_rel_path = oferta.imagen.name
        old_full_path = oferta.imagen.path
        self.assertTrue(os.path.exists(old_full_path))
        self.assertTrue(default_storage.exists(old_rel_path))

        archivo_v2 = SimpleUploadedFile("version_dos.gif", self.gif_bytes, content_type="image/gif")
        oferta.optimistic_update(
            expected_version=1,
            usuario=self.admin,
            accion=AccionAuditoria.ACTUALIZACION,
            imagen=archivo_v2,
        )

        oferta.refresh_from_db()
        self.assertEqual(oferta.version, 2)
        new_rel_path = oferta.imagen.name
        new_full_path = oferta.imagen.path

        # El nuevo archivo debe ser diferente y existir físicamente en disco
        self.assertNotEqual(new_rel_path, old_rel_path)
        self.assertTrue(os.path.exists(new_full_path))
        self.assertTrue(default_storage.exists(new_rel_path))

        # El archivo viejo debe haber sido purgado físicamente del disco
        self.assertFalse(os.path.exists(old_full_path))
        self.assertFalse(default_storage.exists(old_rel_path))

        # Verificar el registro de auditoría
        log_update = AuditLog.objects.filter(
            entidad="OfertaPeriodo",
            registro_id=oferta.pk,
            accion=AccionAuditoria.ACTUALIZACION,
        ).latest("fecha_evento")
        self.assertEqual(log_update.version_resultante, 2)
        self.assertEqual(log_update.cambios_json["imagen"]["antes"], old_rel_path)
        self.assertEqual(log_update.cambios_json["imagen"]["despues"], new_rel_path)

    def test_actualizar_oferta_view_post_reemplaza_archivo_fisico_en_disco(self):
        """
        Verifica que la vista oferta_periodo_update_view procesa multipart/form-data
        correctamente, reemplaza el archivo en disco y purga el archivo obsoleto.
        """
        archivo_inicial = SimpleUploadedFile("primer_flyer.gif", self.gif_bytes, content_type="image/gif")
        oferta = OfertaPeriodo.objects.create(
            titulo="Promo Temporada",
            descripcion="Condiciones estándar",
            periodo="2026-08",
            fecha_inicio=date(2026, 8, 1),
            fecha_fin=date(2026, 8, 31),
            activa=True,
            imagen=archivo_inicial,
        )
        ruta_inicial = oferta.imagen.path
        self.assertTrue(os.path.exists(ruta_inicial))

        archivo_nuevo = SimpleUploadedFile("flyer_renovado.gif", self.gif_bytes, content_type="image/gif")
        datos_update = {
            "version": oferta.version,
            "titulo": "Promo Temporada Renovada",
            "descripcion": "Nuevas condiciones extendidas",
            "periodo": "2026-08",
            "fecha_inicio": "2026-08-01",
            "fecha_fin": "2026-08-31",
            "activa": True,
            "imagen": archivo_nuevo,
        }

        res = self.client.post(
            reverse("oferta_update", args=[oferta.pk]),
            datos_update,
            follow=True,
        )
        self.assertEqual(res.status_code, 200)

        oferta.refresh_from_db()
        self.assertEqual(oferta.version, 2)
        self.assertTrue(os.path.exists(oferta.imagen.path))
        self.assertFalse(os.path.exists(ruta_inicial))

    def test_eliminar_oferta_cancel_delete_view_elimina_archivo_fisico_y_registra_auditoria(self):
        """
        Verifica que al invocar oferta_cancel_delete con action_type='eliminar',
        la oferta se elimina de la base de datos, su archivo gráfico se elimina físicamente del disco
        y se registra la acción ELIMINACION en AuditLog.
        """
        archivo = SimpleUploadedFile("banner_a_borrar.gif", self.gif_bytes, content_type="image/gif")
        oferta = OfertaPeriodo.objects.create(
            titulo="Oferta Para Eliminación",
            descripcion="Será eliminada por completo",
            periodo="2026-09",
            fecha_inicio=date(2026, 9, 1),
            fecha_fin=date(2026, 9, 30),
            activa=True,
            imagen=archivo,
        )
        ruta_archivo = oferta.imagen.path
        nombre_relativo = oferta.imagen.name
        self.assertTrue(os.path.exists(ruta_archivo))
        self.assertTrue(default_storage.exists(nombre_relativo))

        res = self.client.post(
            reverse("oferta_cancel_delete", args=[oferta.pk]),
            {"action_type": "eliminar"},
            follow=True,
        )
        self.assertEqual(res.status_code, 200)

        # La entidad ya no existe en la base de datos
        self.assertFalse(OfertaPeriodo.objects.filter(pk=oferta.pk).exists())

        # El archivo fue eliminado físicamente del disco
        self.assertFalse(os.path.exists(ruta_archivo))
        self.assertFalse(default_storage.exists(nombre_relativo))

        # La bitácora registra la eliminación
        log_del = AuditLog.objects.get(
            entidad="OfertaPeriodo",
            registro_id=oferta.pk,
            accion=AccionAuditoria.ELIMINACION,
        )
        self.assertEqual(log_del.cambios_json.get("titulo"), "Oferta Para Eliminación")

    def test_eliminar_oferta_model_delete_elimina_archivo_fisico_por_senal(self):
        """
        Verifica que el receptor de señal post_delete eliminar_imagen_oferta_en_delete
        elimina el archivo físico de mediafiles al llamarse oferta.delete().
        """
        archivo = SimpleUploadedFile("senal_delete.gif", self.gif_bytes, content_type="image/gif")
        oferta = OfertaPeriodo.objects.create(
            titulo="Oferta Señal Delete",
            descripcion="Prueba directa de post_delete",
            periodo="2026-10",
            fecha_inicio=date(2026, 10, 1),
            fecha_fin=date(2026, 10, 31),
            activa=True,
            imagen=archivo,
        )
        ruta_archivo = oferta.imagen.path
        nombre_relativo = oferta.imagen.name
        self.assertTrue(os.path.exists(ruta_archivo))

        oferta.delete()

        # El archivo físico fue eliminado del disco
        self.assertFalse(os.path.exists(ruta_archivo))
        self.assertFalse(default_storage.exists(nombre_relativo))

    def test_optimistic_update_conflicto_no_elimina_archivo_original_y_limpia_archivo_nuevo(self):
        """
        Verifica que ante un fallo de concurrencia optimista (versión desactualizada):
        1. Se lanza ConcurrentModificationError.
        2. El archivo existente no se borra.
        3. El nuevo archivo temporal que intentó guardarse se limpia de storage.
        """
        archivo_v1 = SimpleUploadedFile("original_protegido.gif", self.gif_bytes, content_type="image/gif")
        oferta = OfertaPeriodo.objects.create(
            titulo="Oferta Concurrente",
            descripcion="Protección de archivos",
            periodo="2026-11",
            fecha_inicio=date(2026, 11, 1),
            fecha_fin=date(2026, 11, 30),
            activa=True,
            imagen=archivo_v1,
        )
        ruta_original = oferta.imagen.path
        self.assertTrue(os.path.exists(ruta_original))

        # Modificación concurrente que sube la versión a 2
        oferta.optimistic_update(
            expected_version=1,
            usuario=self.admin,
            titulo="Oferta Concurrente Editada",
        )
        self.assertEqual(oferta.version, 2)

        # Intento de subir nueva imagen con la versión 1 obsoleta
        archivo_stale = SimpleUploadedFile("intento_stale.gif", self.gif_bytes, content_type="image/gif")
        with self.assertRaises(ConcurrentModificationError):
            oferta.optimistic_update(
                expected_version=1,
                usuario=self.admin,
                imagen=archivo_stale,
            )

        # El archivo original sigue existiendo intacto
        self.assertTrue(os.path.exists(ruta_original))

    def test_limpiar_imagen_con_none_elimina_archivo_fisico(self):
        """
        Verifica que al actualizar una oferta pasando imagen=None, el archivo
        físico existente se elimina de disco y el campo queda en null/vacío.
        """
        archivo = SimpleUploadedFile("a_limpiar.gif", self.gif_bytes, content_type="image/gif")
        oferta = OfertaPeriodo.objects.create(
            titulo="Oferta Con Imagen a Limpiar",
            descripcion="La imagen será removida",
            periodo="2026-12",
            fecha_inicio=date(2026, 12, 1),
            fecha_fin=date(2026, 12, 31),
            activa=True,
            imagen=archivo,
        )
        ruta_archivo = oferta.imagen.path
        nombre_relativo = oferta.imagen.name
        self.assertTrue(os.path.exists(ruta_archivo))

        oferta.optimistic_update(
            expected_version=1,
            usuario=self.admin,
            imagen=None,
        )
        oferta.refresh_from_db()
        self.assertFalse(bool(oferta.imagen))
        self.assertFalse(os.path.exists(ruta_archivo))
        self.assertFalse(default_storage.exists(nombre_relativo))

    def test_oferta_form_widget_y_previsualizacion_sin_clearable_ni_rutas(self):
        """
        Verifica que OfertaPeriodoForm utilice forms.FileInput eliminando la ruta,
        el nombre en texto plano y el checkbox 'limpiar', proporcionando el contenedor
        de previsualización instantánea tanto en creación como en edición.
        """
        from operacion.forms import OfertaPeriodoForm
        from django import forms

        form = OfertaPeriodoForm()
        widget = form.fields["imagen"].widget
        self.assertIsInstance(widget, forms.FileInput)
        self.assertNotIsInstance(widget, forms.ClearableFileInput)
        self.assertEqual(widget.attrs.get("accept"), "image/*")
        self.assertEqual(widget.attrs.get("id"), "id_imagen")

        # 1. Creación: contenedor oculto, sin texto de limpiar ni rutas expuestas
        res_crear = self.client.get(reverse("oferta_create"))
        self.assertEqual(res_crear.status_code, 200)
        contenido_crear = res_crear.content.decode("utf-8")
        self.assertIn("contenedor-previsualizacion-imagen", contenido_crear)
        self.assertIn("img-previsualizacion-oferta", contenido_crear)
        self.assertIn("display:none", contenido_crear)
        self.assertNotIn("imagen-clear", contenido_crear)
        self.assertNotIn("Pieza cargada actualmente", contenido_crear)
        self.assertNotIn("Actualmente:", contenido_crear)

        # 2. Edición: contenedor visible con URL de la imagen, sin checkbox 'limpiar' ni texto de archivo
        archivo = SimpleUploadedFile("preview_test.gif", self.gif_bytes, content_type="image/gif")
        oferta = OfertaPeriodo.objects.create(
            titulo="Oferta Para Preview",
            descripcion="Verificando contenedor UI",
            periodo="2026-11",
            fecha_inicio=date(2026, 11, 1),
            fecha_fin=date(2026, 11, 30),
            activa=True,
            imagen=archivo,
        )
        res_editar = self.client.get(reverse("oferta_update", args=[oferta.pk]))
        self.assertEqual(res_editar.status_code, 200)
        contenido_editar = res_editar.content.decode("utf-8")
        self.assertIn("contenedor-previsualizacion-imagen", contenido_editar)
        self.assertIn(oferta.imagen.url, contenido_editar)
        self.assertNotIn("imagen-clear", contenido_editar)
        self.assertNotIn("Pieza cargada actualmente", contenido_editar)
        self.assertNotIn("Actualmente:", contenido_editar)


