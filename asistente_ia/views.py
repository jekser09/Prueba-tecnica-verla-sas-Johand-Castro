from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from asgiref.sync import sync_to_async
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from asistente_ia.models import AIAuditLog, CasoUsoIA, DecisionHumanaIA
from asistente_ia.services import consultar_gemini, registrar_auditoria_ia
from operacion.models import MetaMensual, OfertaPeriodo
from red_comercial.models import Aliado, Ciudad, Coordinador, EstadoVendedor, Vendedor
from red_comercial.rbac import requerir_roles


async def api_consultar_asistente_view(request: HttpRequest) -> JsonResponse:
    """
    Endpoint asíncrono para el Copiloto Flotante Global.
    Inyecta contexto consciente de la pantalla actual (current_path),
    procesa la consulta mediante gemini-2.5-flash y guarda telemetría en AIAuditLog.
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

    # Inyección asíncrona de contexto de pantalla y negocio
    contexto_negocio = await _construir_contexto_pantalla(current_path)

    system_instruction = (
        "Eres el Asistente Copiloto Oficial del Portal de Aliados Comerciales de VERLA SAS. "
        "Tu propósito es apoyar a la administración, aliados y vendedores en la redacción de copys comerciales "
        "y el análisis de cumplimiento de metas mensuales. "
        "Debes responder de manera profesional, estructurada y en español. "
        "Si generas una oferta, incluye título y descripción listos para copiar. "
        "Si analizas metas, destaca los porcentajes reales y vendedores que requieren refuerzo. "
        f"Contexto actual de la pantalla ({current_path}):\n{contexto_negocio}"
    )

    caso_uso = (
        CasoUsoIA.GENERACION_OFERTA if "oferta" in mensaje_usuario.lower() or caso_uso_solicitado == "OFERTA"
        else CasoUsoIA.ANALISIS_METAS if "meta" in mensaje_usuario.lower() or caso_uso_solicitado == "METAS"
        else CasoUsoIA.GENERACION_OFERTA
    )

    resultado_ia = await consultar_gemini(mensaje_usuario, system_instruction=system_instruction)

    # Resolución asíncrona segura del usuario autenticado (evita SynchronousOnlyOperation al acceder a la sesión)
    def _guardar_log() -> AIAuditLog:
        user = request.user if getattr(request.user, "is_authenticated", False) else None
        return registrar_auditoria_ia(
            usuario=user,
            caso_uso=caso_uso,
            prompt=mensaje_usuario,
            resultado=resultado_ia,
        )

    log = await sync_to_async(_guardar_log)()

    return JsonResponse({
        "ok": True,
        "log_id": log.id,
        "modo": resultado_ia.get("modo"),
        "modelo": resultado_ia.get("modelo"),
        "latencia_ms": resultado_ia.get("latencia_ms"),
        "respuesta": resultado_ia.get("respuesta"),
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
def _construir_contexto_pantalla(current_path: str) -> str:
    """Recolecta métricas en tiempo real según la sección del portal que el usuario está visitando."""
    if "/comercial/" in current_path:
        ciudades = list(Ciudad.objects.filter(activa=True).values_list("nombre", flat=True)[:5])
        aliados = list(Aliado.objects.filter(activo=True).values_list("razon_social", flat=True)[:5])
        vendedores_activos = Vendedor.objects.filter(estado=EstadoVendedor.ACTIVO).count()
        vendedores_bloqueados = Vendedor.objects.filter(estado=EstadoVendedor.BLOQUEADO).count()
        return (
            f"El usuario está en la sección de Red Comercial. Ciudades activas: {', '.join(ciudades)}. "
            f"Aliados principales: {', '.join(aliados)}. Fuerza de ventas: {vendedores_activos} activos, "
            f"{vendedores_bloqueados} bloqueados."
        )

    elif "/operacion/" in current_path:
        periodo = timezone.now().strftime("%Y-%m")
        metas = MetaMensual.objects.filter(periodo=periodo)
        total_meta = sum(m.meta_valor for m in metas)
        total_real = sum(m.resultado_real for m in metas)
        ofertas = list(OfertaPeriodo.objects.filter(periodo=periodo, activa=True).values_list("titulo", flat=True)[:4])
        return (
            f"El usuario está en Operación de Metas & Ofertas para el periodo {periodo}. "
            f"Meta consolidada: ${total_meta}, Ventas reales: ${total_real}. "
            f"Ofertas vigentes del mes: {', '.join(ofertas) if ofertas else 'Ninguna oferta creada aún'}."
        )

    return "El usuario se encuentra navegando en el portal general de VERLA SAS."
