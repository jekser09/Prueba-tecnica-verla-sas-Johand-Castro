from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from asgiref.sync import sync_to_async
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from asistente_ia.models import AIAuditLog, CasoUsoIA, DecisionHumanaIA
from asistente_ia.services import (
    LIMITE_CONSULTAS_2MIN,
    LIMITE_CONSULTAS_DIA,
    consultar_gemini,
    registrar_auditoria_ia,
    verificar_cuota_usuario,
)
from operacion.models import MetaMensual, OfertaPeriodo
from red_comercial.models import Aliado, Ciudad, Coordinador, EstadoVendedor, Vendedor
from red_comercial.rbac import obtener_perfil_actor, requerir_roles


def api_estado_asistente_view(request: HttpRequest) -> JsonResponse:
    """
    Retorna el estado inicial del asistente para la sesión activa:
    rol del usuario, cuotas disponibles (15/2min, 50/día) y mensaje inicial contextualizado.
    """
    perfil = obtener_perfil_actor(request.user)
    cuota = verificar_cuota_usuario(request.user)

    nombre = "Invitado"
    if request.user.is_authenticated:
        if perfil["es_vendedor"] and perfil["objeto"]:
            nombre = perfil["objeto"].nombre_completo
        elif perfil["es_coordinador"] and perfil["objeto"]:
            nombre = perfil["objeto"].nombre_completo
        elif perfil["es_aliado"] and perfil["objeto"]:
            nombre = perfil["objeto"].razon_social
        else:
            nombre = request.user.get_full_name() or request.user.username

    rol_etiqueta = {
        "ADMIN": "Administrador",
        "ALIADO": "Aliado Comercial",
        "COORDINADOR": "Coordinador Comercial",
        "VENDEDOR": "Vendedor",
    }.get(perfil["rol"], "Usuario")

    mensaje_inicial = (
        f"¡Hola {nombre}! Soy tu Copiloto comercial de VERLA SAS ({rol_etiqueta}). "
        f"Tienes **{cuota['restantes_hoy']} de {cuota['limite_dia']} consultas disponibles hoy** "
        f"(máximo {cuota['limite_2min']} cada 2 minutos). "
        "Puedo apoyarte a consultar tus metas, analizar el porcentaje de cumplimiento de ventas, "
        "revisar ofertas vigentes o recomendarte y redactar una nueva oferta comercial. ¿En qué te colaboro hoy?"
    )

    return JsonResponse({
        "ok": True,
        "nombre": nombre,
        "rol": perfil["rol"],
        "rol_etiqueta": rol_etiqueta,
        "cuota": cuota,
        "mensaje_inicial": mensaje_inicial,
    })


async def api_consultar_asistente_view(request: HttpRequest) -> JsonResponse:
    """
    Endpoint asíncrono para el Copiloto Flotante Global.
    Aplica verificación de cuotas (15 cada 2 min, 50 por día), inyecta contexto de usuario
    y pantalla con aislamiento de datos, procesa mediante Gemini/fallback y actualiza métricas.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Método no permitido. Utilice POST."}, status=405)

    try:
        body = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"error": "Cuerpo de solicitud JSON inválido."}, status=400)

    mensaje_usuario = str(body.get("mensaje", "")).strip()
    current_path = str(body.get("current_path", "/"))
    caso_uso_solicitado = body.get("caso_uso", "")

    if not mensaje_usuario:
        return JsonResponse({"error": "El mensaje no puede estar vacío."}, status=400)

    if len(mensaje_usuario) > 400:
        return JsonResponse({"error": "El mensaje excede el límite máximo de 400 caracteres."}, status=400)

    # 1. Verificación de cuota de usuario (15/2min, 50/día)
    def _revisar_cuota():
        return verificar_cuota_usuario(request.user)

    cuota = await sync_to_async(_revisar_cuota)()
    if not cuota["puede_consultar"]:
        return JsonResponse({
            "ok": False,
            "error": cuota["motivo_bloqueo"],
            "cuota": cuota,
        }, status=429)

    # 2. Inyección asíncrona de contexto de usuario y pantalla
    perfil = await sync_to_async(obtener_perfil_actor)(request.user)
    contexto_negocio = await _construir_contexto_pantalla(current_path, request.user)

    system_instruction = (
        "Eres el Asistente Copiloto Oficial del Portal de Aliados Comerciales de VERLA SAS. "
        "Tu propósito es apoyar y asesorar a la administración, aliados, coordinadores y vendedores "
        "con base en los datos oficiales de la empresa. "
        "Debes responder en español, de forma profesional, concisa y estructurada en Markdown legible "
        "(utiliza ### para títulos, **negrita** para métricas o énfasis y viñetas con guiones). "
        "Si te preguntan por metas, KPIs comerciales, cumplimiento o porcentajes, utiliza los datos reales de las herramientas o contexto. "
        "Si te piden redactar o recomendar una oferta, proporciona una propuesta atractiva con: "
        "### 🎁 Nombre de la Oferta\n**Descripción Comercial:** ...\n**Condiciones Clave:** ...\n"
        "Cuando te soliciten consejos, recomendaciones pedagógicas, coaching o estrategias para mejorar el desempeño "
        "de un vendedor o del equipo comercial, tienes plena libertad analítica y creativa para formular sugerencias "
        "prácticas, motivacionales y accionables adaptadas a telecomunicaciones y venta de fibra óptica (ej: técnicas de prospección "
        "en terreno, manejo de objeciones de tarifa/cobertura, planes de recuperación para asesores rezagados y comités de seguimiento).\n"
        "Mantén el rol de asesor con control humano: no ejecutes cambios en la base de datos sin confirmación.\n\n"
        f"Contexto oficial autorizado para esta interacción:\n{contexto_negocio}"
    )

    caso_uso = (
        CasoUsoIA.GENERACION_OFERTA if "oferta" in mensaje_usuario.lower() or caso_uso_solicitado == "OFERTA"
        else CasoUsoIA.ANALISIS_METAS if "meta" in mensaje_usuario.lower() or "cumplimiento" in mensaje_usuario.lower() or caso_uso_solicitado == "METAS"
        else CasoUsoIA.GENERACION_OFERTA
    )

    resultado_ia = await consultar_gemini(
        mensaje_usuario,
        system_instruction=system_instruction,
        contexto_negocio=contexto_negocio,
        perfil_actor=perfil,
    )

    # Guardar auditoría y recalcular cuota actualizada
    def _guardar_log_y_actualizar_cuota() -> tuple[AIAuditLog, dict[str, Any]]:
        user = request.user if getattr(request.user, "is_authenticated", False) else None
        log_obj = registrar_auditoria_ia(
            usuario=user,
            caso_uso=caso_uso,
            prompt=mensaje_usuario,
            resultado=resultado_ia,
        )
        cuota_act = verificar_cuota_usuario(user)
        return log_obj, cuota_act

    log, cuota_actualizada = await sync_to_async(_guardar_log_y_actualizar_cuota)()

    return JsonResponse({
        "ok": True,
        "log_id": log.id,
        "modo": resultado_ia.get("modo"),
        "modelo": resultado_ia.get("modelo"),
        "latencia_ms": resultado_ia.get("latencia_ms"),
        "respuesta": resultado_ia.get("respuesta"),
        "cuota": cuota_actualizada,
    })


@require_POST
def api_veredicto_humano_view(request: HttpRequest) -> JsonResponse:
    """Registra la retroalimentación human-in-the-loop (ACEPTADO, EDITADO, DESCARTADO)."""
    try:
        body = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"error": "JSON inválido."}, status=400)

    log_id = body.get("log_id")
    decision = body.get("decision")

    if not log_id or decision not in DecisionHumanaIA.values:
        return JsonResponse({"error": "Parámetros log_id o decision inválidos."}, status=400)

    log = get_object_or_404(AIAuditLog, pk=log_id)
    log.decision_humana = decision
    log.save()

    return JsonResponse({"ok": True, "log_id": log.id, "decision": log.decision_humana})


@requerir_roles("ADMIN")
def asistente_auditoria_list_view(request: HttpRequest) -> HttpResponse:
    """Vista de supervisión de bitácora de IA, telemetría y decisiones humanas (Exclusiva ADMIN)."""
    logs_qs = AIAuditLog.objects.select_related("usuario").all().order_by("-creado_en")
    paginador = Paginator(logs_qs, 20)
    page_number = request.GET.get("page")
    page_obj = paginador.get_page(page_number)

    return render(request, "asistente_ia/auditoria_list.html", {"page_obj": page_obj})


@sync_to_async
def _construir_contexto_pantalla(current_path: str, user: Any = None) -> str:
    """
    Recolecta métricas en tiempo real con aislamiento de datos según el rol del usuario
    y la sección del portal que está consultando.
    """
    perfil = obtener_perfil_actor(user)
    periodo = timezone.now().strftime("%Y-%m")
    lineas = []

    # 1. Identidad y alcance del actor
    if perfil["es_admin"]:
        lineas.append("ACTOR: Administrador del sistema con visión global de la red comercial VERLA SAS.")
    elif perfil["es_aliado"]:
        aliado = perfil["objeto"]
        lineas.append(f"ACTOR: Aliado Comercial '{aliado.razon_social}' (NIT: {aliado.nit}, Contrato: {aliado.codigo_contrato}).")
    elif perfil["es_coordinador"]:
        coord = perfil["objeto"]
        lineas.append(f"ACTOR: Coordinador '{coord.nombre_completo}' adscrito a '{coord.aliado.razon_social}'.")
    elif perfil["es_vendedor"]:
        vend = perfil["objeto"]
        lineas.append(
            f"ACTOR: Vendedor '{vend.nombre_completo}' (CC: {vend.documento}, Cargo: {vend.cargo}, "
            f"Estado: {vend.estado}, Ciudad base: {vend.ciudad_base.nombre}, "
            f"Coordinador: {vend.coordinador.nombre_completo}, Aliado: {vend.aliado.razon_social})."
        )
    else:
        lineas.append("ACTOR: Usuario del portal comercial.")

    # 2. Metas y cumplimiento según alcance (Data Isolation)
    if perfil["es_vendedor"]:
        meta = MetaMensual.objects.filter(vendedor=perfil["objeto"], periodo=periodo).first()
        if meta:
            pct = round((meta.resultado_real / meta.meta_valor * 100), 1) if meta.meta_valor > 0 else Decimal("0.0")
            lineas.append(
                f"METAS PERSONALES ({periodo}): Asignada: ${meta.meta_valor:,.2f} COP | "
                f"Real: ${meta.resultado_real:,.2f} COP | Cumplimiento: {pct}% | Obs: {meta.observaciones or 'Sin observaciones'}."
            )
        else:
            lineas.append(f"METAS PERSONALES ({periodo}): No registra metas asignadas para el periodo actual.")
    elif perfil["es_coordinador"]:
        metas_coord = MetaMensual.objects.select_related("vendedor").filter(vendedor__coordinador=perfil["objeto"], periodo=periodo)
        tot_meta = sum(m.meta_valor for m in metas_coord)
        tot_real = sum(m.resultado_real for m in metas_coord)
        pct = round((tot_real / tot_meta * 100), 1) if tot_meta > 0 else Decimal("0.0")
        lineas.append(
            f"METAS EQUIPO SUPERVISADO ({periodo}): Total Asignada: ${tot_meta:,.2f} COP | "
            f"Total Real: ${tot_real:,.2f} COP | Cumplimiento global: {pct}% | Vendedores con meta: {metas_coord.count()}."
        )
        detalle_vend = [
            f"{m.vendedor.nombre_completo}: ${m.resultado_real:,.2f}/${m.meta_valor:,.2f} ({round((m.resultado_real/m.meta_valor*100), 1) if m.meta_valor > 0 else 0}%)"
            for m in metas_coord[:5]
        ]
        if detalle_vend:
            lineas.append("Vendedores destacados del equipo: " + "; ".join(detalle_vend))
    elif perfil["es_aliado"]:
        metas_aliado = MetaMensual.objects.filter(vendedor__coordinador__aliado=perfil["objeto"], periodo=periodo)
        tot_meta = sum(m.meta_valor for m in metas_aliado)
        tot_real = sum(m.resultado_real for m in metas_aliado)
        pct = round((tot_real / tot_meta * 100), 1) if tot_meta > 0 else Decimal("0.0")
        lineas.append(
            f"METAS RED ALIADO ({periodo}): Consolidada: ${tot_meta:,.2f} COP | "
            f"Real: ${tot_real:,.2f} COP | Cumplimiento red: {pct}%."
        )
    elif perfil["es_admin"]:
        metas_admin = MetaMensual.objects.filter(periodo=periodo)
        tot_meta = sum(m.meta_valor for m in metas_admin)
        tot_real = sum(m.resultado_real for m in metas_admin)
        pct = round((tot_real / tot_meta * 100), 1) if tot_meta > 0 else Decimal("0.0")
        lineas.append(
            f"METAS NACIONALES ({periodo}): Consolidada: ${tot_meta:,.2f} COP | "
            f"Real: ${tot_real:,.2f} COP | Cumplimiento nacional: {pct}%."
        )

    # 3. Ofertas vigentes aplicables al actor
    ofertas_qs = OfertaPeriodo.objects.filter(periodo=periodo, activa=True)
    if perfil["es_vendedor"]:
        ciudades_ids = [perfil["objeto"].ciudad_base_id] + list(perfil["objeto"].ciudades_operacion.values_list("id", flat=True))
        ofertas_qs = ofertas_qs.filter(ciudades__id__in=ciudades_ids).distinct()
    elif perfil["es_aliado"]:
        ofertas_qs = ofertas_qs.filter(Q(aliado__isnull=True) | Q(aliado=perfil["objeto"])).distinct()

    ofertas_encontradas = list(ofertas_qs[:4])
    if ofertas_encontradas:
        lineas.append(f"OFERTAS VIGENTES DISPONIBLES ({periodo}):")
        for o in ofertas_encontradas:
            lineas.append(f"- '{o.titulo}' (Vigencia: {o.fecha_inicio} a {o.fecha_fin}): {o.descripcion[:140]}")
    else:
        lineas.append("OFERTAS VIGENTES: No hay ofertas activas en el periodo para esta cobertura.")

    # 4. Vendedores bloqueados o inactivos (Alertas operativas)
    if perfil["es_admin"]:
        bloqueados = list(Vendedor.objects.select_related("coordinador", "ciudad_base").filter(estado=EstadoVendedor.BLOQUEADO))
        inactivos = list(Vendedor.objects.select_related("coordinador", "ciudad_base").filter(estado=EstadoVendedor.INACTIVO))
        if bloqueados:
            lineas.append("VENDEDORES BLOQUEADOS ACTUALMENTE EN LA RED:")
            for v in bloqueados:
                lineas.append(
                    f"- {v.nombre_completo} (Cédula: {v.documento}, Ciudad: {v.ciudad_base.nombre}, "
                    f"Coordinador: {v.coordinador.nombre_completo}, Motivo: '{v.motivo_estado or 'Sin motivo'}')"
                )
        else:
            lineas.append("VENDEDORES BLOQUEADOS: No hay vendedores bloqueados actualmente.")

        if inactivos:
            lineas.append("VENDEDORES INACTIVOS ACTUALMENTE EN LA RED:")
            for v in inactivos:
                lineas.append(
                    f"- {v.nombre_completo} (Cédula: {v.documento}, Ciudad: {v.ciudad_base.nombre}, "
                    f"Coordinador: {v.coordinador.nombre_completo}, Motivo: '{v.motivo_estado or 'Sin motivo'}')"
                )
        else:
            lineas.append("VENDEDORES INACTIVOS: No hay vendedores inactivos actualmente.")

    elif perfil["es_coordinador"]:
        bloqueados = list(Vendedor.objects.filter(coordinador=perfil["objeto"], estado=EstadoVendedor.BLOQUEADO))
        inactivos = list(Vendedor.objects.filter(coordinador=perfil["objeto"], estado=EstadoVendedor.INACTIVO))
        if bloqueados:
            lineas.append("VENDEDORES BLOQUEADOS EN TU EQUIPO: " + ", ".join(f"{v.nombre_completo} ({v.motivo_estado})" for v in bloqueados))
        else:
            lineas.append("VENDEDORES BLOQUEADOS EN TU EQUIPO: Ninguno.")
        if inactivos:
            lineas.append("VENDEDORES INACTIVOS EN TU EQUIPO: " + ", ".join(f"{v.nombre_completo} ({v.motivo_estado})" for v in inactivos))
        else:
            lineas.append("VENDEDORES INACTIVOS EN TU EQUIPO: Ninguno.")

    elif perfil["es_aliado"]:
        bloqueados = list(Vendedor.objects.filter(coordinador__aliado=perfil["objeto"], estado=EstadoVendedor.BLOQUEADO))
        inactivos = list(Vendedor.objects.filter(coordinador__aliado=perfil["objeto"], estado=EstadoVendedor.INACTIVO))
        if bloqueados:
            lineas.append("VENDEDORES BLOQUEADOS EN TU RED: " + ", ".join(f"{v.nombre_completo} ({v.motivo_estado})" for v in bloqueados))
        else:
            lineas.append("VENDEDORES BLOQUEADOS EN TU RED: Ninguno.")
        if inactivos:
            lineas.append("VENDEDORES INACTIVOS EN TU RED: " + ", ".join(f"{v.nombre_completo} ({v.motivo_estado})" for v in inactivos))
        else:
            lineas.append("VENDEDORES INACTIVOS EN TU RED: Ninguno.")

    # 5. Contexto de pantalla
    lineas.append(f"UBICACIÓN EN PORTAL: El usuario está navegando en la ruta '{current_path}'.")

    return "\n".join(lineas)
