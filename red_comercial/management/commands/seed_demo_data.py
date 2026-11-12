from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from operacion.models import MetaMensual, OfertaPeriodo
from red_comercial.models import Aliado, Ciudad, Coordinador, EstadoVendedor, Vendedor

User = get_user_model()


class Command(BaseCommand):
    help = "Puebla la base de datos con un escenario comercial representativo: al menos 5 ciudades, 10 aliados, 3 coordinadores y 10 vendedores con metas y ofertas."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Iniciando sembrado de datos demo para VERLA SAS..."))

        # ==============================================================================
        # 1. CATÁLOGO DE CIUDADES (5 CIUDADES)
        # ==============================================================================
        ciudades_data = [
            ("BOG", "Bogotá D.C.", "Cundinamarca"),
            ("MED", "Medellín", "Antioquia"),
            ("CLO", "Cali", "Valle del Cauca"),
            ("BAQ", "Barranquilla", "Atlántico"),
            ("BUC", "Bucaramanga", "Santander"),
        ]
        ciudades = {}
        for cod, nom, dep in ciudades_data:
            c, _ = Ciudad.objects.get_or_create(
                codigo=cod,
                defaults={"nombre": nom, "departamento": dep, "activa": True},
            )
            ciudades[cod] = c
        self.stdout.write(self.style.SUCCESS(f"✓ {len(ciudades)} Ciudades verificadas/creadas."))

        # ==============================================================================
        # 2. ALIADOS COMERCIALES (10 ALIADOS)
        # ==============================================================================
        aliados_data = [
            ("900100101-1", "Distribuciones Andinas SAS", "CTR-AND-01", "contacto@andina.com", "3101234567"),
            ("900200202-2", "Conectividad del Pacífico SAS", "CTR-PAC-02", "contacto@pacifico.com", "3157654321"),
            ("900300303-3", "Redes del Caribe y Cía SAS", "CTR-CAR-03", "info@redesdelcaribe.com", "3001112233"),
            ("900400404-4", "Servicios Ópticos de Antioquia SAS", "CTR-ANT-04", "comercial@opticosantioquia.com", "3124445566"),
            ("900500505-5", "Soluciones Digitales del Valle SAS", "CTR-VAL-05", "ventas@solucionesvalle.co", "3189990011"),
            ("900600606-6", "Telecomunicaciones Santander SAS", "CTR-SAN-06", "atencion@telesantander.com", "3172223344"),
            ("900700707-7", "Enlace Central de Comunicaciones SAS", "CTR-CEN-07", "contacto@enlacecentral.co", "3145556677"),
            ("900800808-8", "Aliado Metropolitano BOG SAS", "CTR-MET-08", "info@aliadobog.com", "3118889900"),
            ("900900909-9", "Fuerza Comercial de la Sabana SAS", "CTR-SAB-09", "ventas@fuerzasabana.com", "3163334455"),
            ("900010010-0", "Comunicaciones de Oriente SAS", "CTR-ORI-10", "gerencia@comoriente.co", "3137778899"),
        ]
        aliados = []
        for nit, razon, contrato, correo, tel in aliados_data:
            a, _ = Aliado.objects.get_or_create(
                nit=nit,
                defaults={
                    "razon_social": razon,
                    "codigo_contrato": contrato,
                    "correo_contacto": correo,
                    "telefono": tel,
                    "activo": True,
                },
            )
            aliados.append(a)
        self.stdout.write(self.style.SUCCESS(f"✓ {len(aliados)} Aliados comerciales listos."))

        # ==============================================================================
        # 3. COORDINADORES COMERCIALES (3 COORDINADORES)
        # ==============================================================================
        coordinadores_data = [
            ("CC-COORD-001", "Carlos Mendoza Coordinador", "carlos.mendoza@andina.com", "3119876543", aliados[0]),
            ("CC-COORD-002", "Elena Restrepo Coordinadora", "elena.restrepo@pacifico.com", "3128887766", aliados[1]),
            ("CC-COORD-003", "Andrés Morales Coordinador", "andres.morales@caribe.com", "3004445566", aliados[2]),
        ]
        coordinadores = []
        for doc, nom, mail, tel, aliado_resp in coordinadores_data:
            co, _ = Coordinador.objects.get_or_create(
                documento=doc,
                defaults={
                    "aliado": aliado_resp,
                    "nombre_completo": nom,
                    "correo": mail,
                    "telefono": tel,
                    "activo": True,
                },
            )
            coordinadores.append(co)
        self.stdout.write(self.style.SUCCESS(f"✓ {len(coordinadores)} Coordinadores comerciales listos."))

        # ==============================================================================
        # 4. FUERZA DE VENTAS (10 VENDEDORES: ACTIVOS, MULTICIUDAD Y BLOQUEADOS)
        # ==============================================================================
        vendedores_data = [
            # Coordinador 0 (Carlos Mendoza - Aliados[0] Andina)
            ("CC-VEND-ACTIVO", "Laura Gómez Vendedora", "laura.gomez@andina.com", "3201112233", "Asesor Comercial Senior", ciudades["BOG"], [ciudades["BOG"], ciudades["MED"]], EstadoVendedor.ACTIVO, "", coordinadores[0]),
            ("CC-VEND-BLOQUEADO", "Pedro Restrepo Bloqueado", "pedro.restrepo@andina.com", "3209998877", "Asesor Comercial Junior", ciudades["BOG"], [ciudades["BOG"]], EstadoVendedor.BLOQUEADO, "Incumplimiento reiterado de entregas y cobranzas.", coordinadores[0]),
            ("CC-VEND-003", "Sofía Hernández", "sofia.hernandez@andina.com", "3213334455", "Consultor Hogar", ciudades["MED"], [ciudades["MED"], ciudades["CLO"]], EstadoVendedor.ACTIVO, "", coordinadores[0]),
            ("CC-VEND-004", "Javier Castillo", "javier.castillo@andina.com", "3225556677", "Asesor Corporativo", ciudades["BOG"], [ciudades["BOG"], ciudades["BUC"]], EstadoVendedor.ACTIVO, "", coordinadores[0]),

            # Coordinador 1 (Elena Restrepo - Aliados[1] Pacífico)
            ("CC-VEND-005", "Marcos Valencia", "marcos.valencia@pacifico.com", "3176665544", "Consultor Pyme", ciudades["CLO"], [ciudades["CLO"]], EstadoVendedor.ACTIVO, "", coordinadores[1]),
            ("CC-VEND-006", "Camila Ortiz", "camila.ortiz@pacifico.com", "3187778899", "Ejecutiva de Cuentas", ciudades["CLO"], [ciudades["CLO"], ciudades["BOG"]], EstadoVendedor.ACTIVO, "", coordinadores[1]),
            ("CC-VEND-007", "Felipe Salcedo", "felipe.salcedo@pacifico.com", "3191112244", "Asesor Fibra Residencial", ciudades["CLO"], [ciudades["CLO"]], EstadoVendedor.INACTIVO, "Licencia médica temporal no remunerada.", coordinadores[1]),

            # Coordinador 2 (Andrés Morales - Aliados[2] Caribe)
            ("CC-VEND-008", "Diana Arismendi", "diana.arismendi@caribe.com", "3007771122", "Asesora Senior Caribe", ciudades["BAQ"], [ciudades["BAQ"]], EstadoVendedor.ACTIVO, "", coordinadores[2]),
            ("CC-VEND-009", "Manuel Orozco", "manuel.orozco@caribe.com", "3018882233", "Especialista Pyme Costa", ciudades["BAQ"], [ciudades["BAQ"], ciudades["BUC"]], EstadoVendedor.ACTIVO, "", coordinadores[2]),
            ("CC-VEND-010", "Lorena Barrientos", "lorena.barrientos@caribe.com", "3029993344", "Asesora Ventas Terreno", ciudades["BUC"], [ciudades["BUC"]], EstadoVendedor.ACTIVO, "", coordinadores[2]),
        ]

        base_creacion = timezone.now() - timedelta(days=120)
        vendedores = []
        for idx, (doc, nom, mail, tel, cargo, c_base, c_oper, estado, motivo, coord_v) in enumerate(vendedores_data):
            # Fecha de creación y registro calculada con datetime
            fecha_creacion_dt = base_creacion + timedelta(days=idx * 10, hours=idx * 2, minutes=idx * 15)
            v, _ = Vendedor.objects.get_or_create(
                documento=doc,
                defaults={
                    "coordinador": coord_v,
                    "nombre_completo": nom,
                    "correo": mail,
                    "telefono": tel,
                    "cargo": cargo,
                    "ciudad_base": c_base,
                    "estado": estado,
                    "motivo_estado": motivo,
                    "fecha_ingreso": fecha_creacion_dt.date(),
                },
            )
            v.ciudades_operacion.set(c_oper)
            Vendedor.objects.filter(pk=v.pk).update(
                creado_en=fecha_creacion_dt,
                fecha_ingreso=fecha_creacion_dt.date(),
            )
            v.refresh_from_db()
            vendedores.append(v)
        self.stdout.write(self.style.SUCCESS(f"✓ {len(vendedores)} Vendedores registrados (activos, inactivos, bloqueados y multiciudad)."))

        # ==============================================================================
        # 5. METAS MENSUALES (PERIODO ACTUAL)
        # ==============================================================================
        periodo_actual = timezone.now().strftime("%Y-%m")
        metas_config = [
            (vendedores[0], Decimal("25000000.00"), Decimal("28500000.00"), "Superó meta de fibra corporativa."),
            (vendedores[2], Decimal("16000000.00"), Decimal("15200000.00"), "Cierre estable de mes."),
            (vendedores[3], Decimal("30000000.00"), Decimal("22000000.00"), "Brecha en contratos de gobierno."),
            (vendedores[4], Decimal("18000000.00"), Decimal("12500000.00"), "Retraso en clientes Pyme Cali."),
            (vendedores[5], Decimal("20000000.00"), Decimal("21800000.00"), "Excelente tasa de cierre."),
            (vendedores[7], Decimal("22000000.00"), Decimal("24500000.00"), "Superó meta en Barranquilla."),
            (vendedores[8], Decimal("14000000.00"), Decimal("9500000.00"), "Requiere refuerzo comercial."),
            (vendedores[9], Decimal("15000000.00"), Decimal("16200000.00"), "Crecimiento en Bucaramanga."),
        ]
        for vend, meta_val, real_val, obs in metas_config:
            MetaMensual.objects.get_or_create(
                vendedor=vend,
                periodo=periodo_actual,
                defaults={
                    "meta_valor": meta_val,
                    "resultado_real": real_val,
                    "observaciones": obs,
                },
            )
        self.stdout.write(self.style.SUCCESS(f"✓ Metas mensuales registradas para {len(metas_config)} asesores en {periodo_actual}."))

        # ==============================================================================
        # 6. OFERTAS COMERCIALES DEL PERIODO
        # ==============================================================================
        hoy = timezone.localdate()
        fin_mes = hoy.replace(day=28)

        of_fibra, _ = OfertaPeriodo.objects.get_or_create(
            titulo="Bono Fibra Óptica 500MB Simétrica",
            periodo=periodo_actual,
            defaults={
                "descripcion": "Instalación gratis y 20% de descuento durante los primeros 3 meses para nuevos suscriptores.",
                "fecha_inicio": hoy,
                "fecha_fin": fin_mes,
                "activa": True,
                "aliado": aliados[0],
            },
        )
        of_fibra.ciudades.set([ciudades["BOG"], ciudades["MED"]])

        of_pyme, _ = OfertaPeriodo.objects.get_or_create(
            titulo="Plan Enlace Dedicado Pyme Pacífico",
            periodo=periodo_actual,
            defaults={
                "descripcion": "Enlace empresarial con IP fija gratuita y soporte de alta disponibilidad para empresas en el Valle.",
                "fecha_inicio": hoy,
                "fecha_fin": fin_mes,
                "activa": True,
                "aliado": aliados[1],
            },
        )
        of_pyme.ciudades.set([ciudades["CLO"]])

        of_caribe, _ = OfertaPeriodo.objects.get_or_create(
            titulo="Promo Costa Conectada 300MB",
            periodo=periodo_actual,
            defaults={
                "descripcion": "Tarifa especial caribeña para clientes residenciales en Barranquilla y Bucaramanga.",
                "fecha_inicio": hoy,
                "fecha_fin": fin_mes,
                "activa": True,
                "aliado": aliados[2],
            },
        )
        of_caribe.ciudades.set([ciudades["BAQ"], ciudades["BUC"]])

        self.stdout.write(self.style.SUCCESS("✓ Ofertas comerciales activas registradas con segmentación."))
        self.stdout.write(self.style.SUCCESS("🎉 Sembrado completo: 5 ciudades, 10 aliados, 3 coordinadores y 10 vendedores listos para auditoría."))
