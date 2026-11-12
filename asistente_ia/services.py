from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
import json
import re
import time
from typing import Any

from decouple import config
import httpx
from asgiref.sync import sync_to_async
from django.db.models import Q
from django.utils import timezone

from asistente_ia.models import AIAuditLog, CasoUsoIA, DecisionHumanaIA
from operacion.models import MetaMensual, OfertaPeriodo
from red_comercial.models import EstadoVendedor, Vendedor


GEMINI_MODEL = "gemini-3.5-flash-lite"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
REQUEST_TIMEOUT_SECONDS = 15.0
LIMITE_CONSULTAS_2MIN = 15
LIMITE_CONSULTAS_DIA = 50
MAX_OUTPUT_TOKENS = 1200

# Declaración de Herramientas (Function Calling) nativas para Google Gemini
GEMINI_TOOLS: list[dict[str, Any]] = [
    {
        "functionDeclarations": [
            {
                "name": "consultar_vendedores",
                "description": (
                    "Consulta vendedores en la base de datos oficial de VERLA SAS según su estado operativo "
                    "(bloqueado, inactivo, activo o no_activos)."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "estado": {
                            "type": "STRING",
                            "description": "Estado de los vendedores a buscar: 'bloqueado', 'inactivo', 'activo' o 'no_activos'",
                            "enum": ["bloqueado", "inactivo", "activo", "no_activos"],
                        }
                    },
                    "required": ["estado"],
                },
            },
            {
                "name": "consultar_metas",
                "description": (
                    "Consulta las metas comerciales, KPIs generales (meta total, ventas reales, porcentaje global, "
                    "brecha y vendedores en alerta) y el desglose de metas y porcentajes por vendedor para el periodo."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "periodo": {
                            "type": "STRING",
                            "description": "Periodo a consultar en formato YYYY-MM, o 'actual'",
                        }
                    },
                },
            },
            {
                "name": "consultar_ofertas",
                "description": (
                    "Consulta ofertas comerciales vigentes en el periodo para la cobertura del actor, "
                    "o solicita redactar/recomendar una nueva oferta atractiva con condiciones clave."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "accion": {
                            "type": "STRING",
                            "description": "'vigentes' para consultar ofertas activas, o 'redactar_nueva' para generar propuesta comercial",
                            "enum": ["vigentes", "redactar_nueva"],
                        }
                    },
                    "required": ["accion"],
                },
            },
        ]
    }
]


def verificar_cuota_usuario(usuario: Any) -> dict[str, Any]:
    """
    Verifica las cuotas de consumo de IA para el usuario:
    - Máximo 15 consultas cada 2 minutos.
    - Máximo 50 consultas por día calendario (00:00:00 a 23:59:59).
    SOLO se descuentan las consultas que efectivamente consumieron llamados a la API de Google
    (tokens_estimados > 0 y modelo != 'reglas-contingencia-v1').
    """
    if not getattr(usuario, "is_authenticated", False):
        return {
            "puede_consultar": True,
            "motivo_bloqueo": None,
            "consumidas_hoy": 0,
            "restantes_hoy": LIMITE_CONSULTAS_DIA,
            "limite_dia": LIMITE_CONSULTAS_DIA,
            "consumidas_2min": 0,
            "restantes_2min": LIMITE_CONSULTAS_2MIN,
            "limite_2min": LIMITE_CONSULTAS_2MIN,
        }

    ahora = timezone.now()
    inicio_dia = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    hace_2_min = ahora - timedelta(minutes=2)

    consultas_hoy = AIAuditLog.objects.filter(
        usuario=usuario,
        creado_en__gte=inicio_dia,
        tokens_estimados__gt=0,
    ).exclude(
        modelo="reglas-contingencia-v1",
    ).count()

    consultas_2min = AIAuditLog.objects.filter(
        usuario=usuario,
        creado_en__gte=hace_2_min,
        tokens_estimados__gt=0,
    ).exclude(
        modelo="reglas-contingencia-v1",
    ).count()

    restantes_hoy = max(0, LIMITE_CONSULTAS_DIA - consultas_hoy)
    restantes_2min = max(0, LIMITE_CONSULTAS_2MIN - consultas_2min)

    puede_consultar = True
    motivo_bloqueo = None

    if consultas_hoy >= LIMITE_CONSULTAS_DIA:
        puede_consultar = False
        motivo_bloqueo = (
            f"Has alcanzado el límite diario de {LIMITE_CONSULTAS_DIA} consultas con el Asistente IA. "
            "Tu cuota se reiniciará automáticamente a la medianoche."
        )
    elif consultas_2min >= LIMITE_CONSULTAS_2MIN:
        puede_consultar = False
        motivo_bloqueo = (
            f"Has alcanzado el límite de {LIMITE_CONSULTAS_2MIN} consultas cada 2 minutos para racionar la cuota de tokens. "
            "Por favor espera unos instantes antes de enviar otra consulta."
        )

    return {
        "puede_consultar": puede_consultar,
        "motivo_bloqueo": motivo_bloqueo,
        "consumidas_hoy": consultas_hoy,
        "restantes_hoy": restantes_hoy,
        "limite_dia": LIMITE_CONSULTAS_DIA,
        "consumidas_2min": consultas_2min,
        "restantes_2min": restantes_2min,
        "limite_2min": LIMITE_CONSULTAS_2MIN,
    }


# ============================================================================
# HERRAMIENTAS DE DOMINIO COMERCIAL (EJECUCIÓN DIRECTA SOBRE ORM)
# ============================================================================

def ejecutar_consulta_vendedores(estado: str = "bloqueado", perfil_actor: dict[str, Any] | None = None) -> dict[str, Any]:
    """Consulta vendedores en tiempo real aplicando aislamiento de datos por rol."""
    estado_normalizado = str(estado).lower().strip()

    if "inactiv" in estado_normalizado:
        estados_buscar = [EstadoVendedor.INACTIVO]
        titulo = "⚠️ Vendedores Inactivos en el Sistema"
        icono = "⚠️"
        etiqueta = "inactivos"
    elif "activ" in estado_normalizado and "no" not in estado_normalizado:
        estados_buscar = [EstadoVendedor.ACTIVO]
        titulo = "✅ Vendedores Activos en el Sistema"
        icono = "✅"
        etiqueta = "activos"
    elif "no" in estado_normalizado or "todos" in estado_normalizado:
        estados_buscar = [EstadoVendedor.BLOQUEADO, EstadoVendedor.INACTIVO]
        titulo = "📋 Vendedores No Operativos (Bloqueados e Inactivos)"
        icono = "🔍"
        etiqueta = "bloqueados o inactivos"
    else:
        estados_buscar = [EstadoVendedor.BLOQUEADO]
        titulo = "🚫 Vendedores Bloqueados en el Sistema"
        icono = "🚫"
        etiqueta = "bloqueados"

    qs = Vendedor.objects.select_related("coordinador", "coordinador__aliado", "ciudad_base").all()

    # Aislamiento según actor
    if perfil_actor and perfil_actor.get("es_coordinador") and perfil_actor.get("objeto"):
        qs = qs.filter(coordinador=perfil_actor["objeto"])
    elif perfil_actor and perfil_actor.get("es_aliado") and perfil_actor.get("objeto"):
        qs = qs.filter(coordinador__aliado=perfil_actor["objeto"])
    elif perfil_actor and perfil_actor.get("es_vendedor") and perfil_actor.get("objeto"):
        qs = qs.filter(coordinador=perfil_actor["objeto"].coordinador)

    vendedores = list(qs.filter(estado__in=estados_buscar).order_by("-actualizado_en"))

    datos_vendedores = []
    detalles_md = []
    for v in vendedores:
        badge = "🔴 BLOQUEADO" if v.estado == EstadoVendedor.BLOQUEADO else "🟠 INACTIVO" if v.estado == EstadoVendedor.INACTIVO else "🟢 ACTIVO"
        item = {
            "nombre_completo": v.nombre_completo,
            "documento": v.documento,
            "cargo": v.cargo,
            "estado": v.estado,
            "ciudad_base": v.ciudad_base.nombre,
            "coordinador": v.coordinador.nombre_completo,
            "aliado": v.coordinador.aliado.razon_social,
            "motivo_estado": v.motivo_estado or "Sin motivo registrado",
        }
        datos_vendedores.append(item)
        detalles_md.append(
            f"{icono} **{v.nombre_completo}** — `{badge}`\n"
            f"- **Documento:** `{v.documento}` | **Cargo:** {v.cargo}\n"
            f"- **Ciudad base:** {v.ciudad_base.nombre}\n"
            f"- **Coordinador:** {v.coordinador.nombre_completo} ({v.coordinador.aliado.razon_social})\n"
            f"- **Motivo del estado:** *{v.motivo_estado or 'Sin motivo registrado'}*"
        )

    if vendedores:
        texto_md = (
            f"### {titulo}\n\n"
            f"Se registran **{len(vendedores)}** vendedor(es) {etiqueta} en tu ámbito de supervisión:\n\n"
            + "\n\n".join(detalles_md) +
            "\n\n*Nota operativa:* Los vendedores bloqueados o inactivos no pueden comercializar ofertas ni acceder a la operación comercial."
        )
    else:
        texto_md = f"✅ Actualmente **no hay vendedores {etiqueta}** en tu ámbito de cobertura autorizado."

    return {
        "datos": {
            "total": len(vendedores),
            "estado_consultado": etiqueta,
            "vendedores": datos_vendedores,
        },
        "texto_markdown": texto_md,
    }


def ejecutar_consulta_metas(periodo: str | None = None, perfil_actor: dict[str, Any] | None = None) -> dict[str, Any]:
    """Consulta metas, KPIs comerciales consolidados y desglose individual por vendedor."""
    periodo_actual = periodo if periodo and periodo != "actual" else timezone.now().strftime("%Y-%m")
    qs = MetaMensual.objects.select_related("vendedor", "vendedor__coordinador", "vendedor__coordinador__aliado", "vendedor__ciudad_base").all()

    if not qs.filter(periodo=periodo_actual).exists():
        periodo_disp = qs.order_by("-periodo").values_list("periodo", flat=True).first()
        if periodo_disp:
            periodo_actual = periodo_disp

    qs = qs.filter(periodo=periodo_actual)

    ambito_txt = "Consolidado Nacional"
    if perfil_actor and perfil_actor.get("es_vendedor") and perfil_actor.get("objeto"):
        qs = qs.filter(vendedor=perfil_actor["objeto"])
        ambito_txt = f"Personal ({perfil_actor['objeto'].nombre_completo})"
    elif perfil_actor and perfil_actor.get("es_coordinador") and perfil_actor.get("objeto"):
        qs = qs.filter(vendedor__coordinador=perfil_actor["objeto"])
        ambito_txt = f"Equipo Coordinador ({perfil_actor['objeto'].nombre_completo})"
    elif perfil_actor and perfil_actor.get("es_aliado") and perfil_actor.get("objeto"):
        qs = qs.filter(vendedor__coordinador__aliado=perfil_actor["objeto"])
        ambito_txt = f"Red Aliado ({perfil_actor['objeto'].razon_social})"

    tot_meta = sum(m.meta_valor for m in qs)
    tot_real = sum(m.resultado_real for m in qs)
    pct = round((tot_real / tot_meta * 100), 1) if tot_meta > 0 else Decimal("0.0")
    brecha = max(Decimal("0.00"), tot_meta - tot_real)

    vendedores_detalle = []
    vendedores_en_alerta = 0
    vendedores_meta_cumplida = 0
    detalles_md = []

    for m in list(qs.order_by("-resultado_real")):
        pct_ind = round((m.resultado_real / m.meta_valor * 100), 1) if m.meta_valor > 0 else Decimal("0.0")
        if pct_ind >= 100:
            estado_desempeno = "CUMPLIDA (>=100%)"
            vendedores_meta_cumplida += 1
            icono = "🟢"
        elif pct_ind >= 80:
            estado_desempeno = "EN_CURSO (80-99%)"
            icono = "🟡"
        else:
            estado_desempeno = "EN_ALERTA (<80%)"
            vendedores_en_alerta += 1
            icono = "🔴"

        vendedores_detalle.append({
            "vendedor": m.vendedor.nombre_completo,
            "documento": m.vendedor.documento,
            "ciudad": m.vendedor.ciudad_base.nombre,
            "meta_valor": float(m.meta_valor),
            "resultado_real": float(m.resultado_real),
            "porcentaje_cumplimiento": float(pct_ind),
            "estado": estado_desempeno,
        })
        detalles_md.append(
            f"{icono} **{m.vendedor.nombre_completo}** ({m.vendedor.ciudad_base.nombre}): "
            f"${m.resultado_real:,.2f} / ${m.meta_valor:,.2f} COP (**{pct_ind}%**)"
        )

    promedio_ventas = round(tot_real / len(vendedores_detalle), 2) if vendedores_detalle else Decimal("0.00")

    if qs.exists():
        txt_vendedores = "\n\n**Desglose de Metas por Vendedor:**\n" + "\n".join(detalles_md) if detalles_md else ""
        texto_md = (
            f"### 📊 Diagnóstico y KPIs Comerciales ({periodo_actual})\n\n"
            f"- **Ámbito de Supervisión:** {ambito_txt}\n"
            f"- **Meta Consolidada:** ${tot_meta:,.2f} COP\n"
            f"- **Ventas Reales Alcanzadas:** ${tot_real:,.2f} COP\n"
            f"- **Porcentaje de Cumplimiento:** **{pct}%**\n"
            f"- **Brecha por Cerrar:** ${brecha:,.2f} COP\n"
            f"- **Total Asesores Evaluados:** {len(vendedores_detalle)} "
            f"(🟢 {vendedores_meta_cumplida} con meta superada | 🔴 {vendedores_en_alerta} en alerta <80%)\n"
            f"- **Promedio de Ventas por Asesor:** ${promedio_ventas:,.2f} COP"
            f"{txt_vendedores}\n\n"
            "**Recomendaciones Comerciales y Coaching:**\n"
            "1. Realizar acompañamiento personalizado y clínicas de objeciones a los asesores en alerta (<80%).\n"
            "2. Apoyar el cierre de ciclo impulsando las ofertas activas de mayor comisión en zonas con brecha.\n"
            "3. Replicar las mejores prácticas de los asesores con meta cumplida en el equipo."
        )
    else:
        texto_md = (
            f"### 📊 Metas de Ventas ({periodo_actual})\n\n"
            f"No se registran metas comerciales configuradas para el periodo **{periodo_actual}** "
            f"en el ámbito seleccionado ({ambito_txt})."
        )

    return {
        "datos": {
            "periodo": periodo_actual,
            "ambito": ambito_txt,
            "meta_total": float(tot_meta),
            "resultado_real_total": float(tot_real),
            "porcentaje_cumplimiento": float(pct),
            "brecha_por_cerrar": float(brecha),
            "total_vendedores": len(vendedores_detalle),
            "vendedores_meta_cumplida": vendedores_meta_cumplida,
            "vendedores_en_alerta": vendedores_en_alerta,
            "promedio_ventas_por_vendedor": float(promedio_ventas),
            "detalle_vendedores": vendedores_detalle,
        },
        "texto_markdown": texto_md,
    }


def ejecutar_consulta_ofertas(accion: str = "vigentes", perfil_actor: dict[str, Any] | None = None) -> dict[str, Any]:
    """Consulta ofertas vigentes o redacta una nueva propuesta comercial."""
    periodo_actual = timezone.now().strftime("%Y-%m")
    qs = OfertaPeriodo.objects.filter(activa=True)

    if not qs.filter(periodo=periodo_actual).exists():
        periodo_disp = qs.order_by("-periodo").values_list("periodo", flat=True).first()
        if periodo_disp:
            periodo_actual = periodo_disp

    qs = qs.filter(periodo=periodo_actual)

    if perfil_actor and perfil_actor.get("es_vendedor") and perfil_actor.get("objeto"):
        v = perfil_actor["objeto"]
        cids = [v.ciudad_base_id] + list(v.ciudades_operacion.values_list("id", flat=True))
        qs = qs.filter(ciudades__id__in=cids).distinct()
    elif perfil_actor and perfil_actor.get("es_aliado") and perfil_actor.get("objeto"):
        qs = qs.filter(Q(aliado__isnull=True) | Q(aliado=perfil_actor["objeto"])).distinct()

    ofertas_activas = list(qs[:4])

    if accion == "redactar_nueva" or not ofertas_activas:
        ofertas_txt = ""
        if ofertas_activas:
            ofertas_txt = "\n\n**Ofertas vigentes actualmente en el sistema:**\n" + "\n".join(
                f"- **{o.titulo}**: {o.descripcion[:120]} (Vigencia: {o.fecha_inicio} a {o.fecha_fin})"
                for o in ofertas_activas
            )

        texto_md = (
            "### 🎁 Propuesta Comercial: Super Fibra Óptica 500MB + TV Pro HD\n\n"
            "**Descripción Comercial:**\n"
            "¡Impulsa tu conectividad con VERLA SAS! Obtén 500 Megas 100% simétricas con costo de instalación preferencial "
            "y 20% de descuento durante los primeros 3 meses de servicio para clientes residenciales y comerciales activos.\n\n"
            "**Condiciones Clave:**\n"
            "- Velocidad 100% simétrica con soporte prioritario 24/7.\n"
            "- Instalación garantizada en menos de 48 horas hábiles en ciudades con cobertura técnica.\n"
            "- Comisión preferencial por venta cerrada para asesores comerciales activos."
            + ofertas_txt
        )
        return {
            "datos": {
                "tipo": "propuesta_redactada",
                "titulo_sugerido": "Super Fibra Óptica 500MB + TV Pro HD",
                "descripcion": "¡Impulsa tu conectividad con VERLA SAS! 500 Megas simétricas con 20% de descuento.",
                "descripcion_comercial": "¡Impulsa tu conectividad con VERLA SAS! 500 Megas simétricas con 20% de descuento.",
                "puntos_clave": [
                    "Velocidad 100% simétrica con soporte prioritario 24/7.",
                    "Instalación garantizada en menos de 48 horas hábiles.",
                    "Comisión preferencial por venta cerrada para asesores.",
                ],
            },
            "texto_markdown": texto_md,
        }
    else:
        lista_md = []
        ofertas_datos = []
        for o in ofertas_activas:
            ofertas_datos.append({
                "id": o.id,
                "titulo": o.titulo,
                "periodo": o.periodo,
                "fecha_inicio": str(o.fecha_inicio),
                "fecha_fin": str(o.fecha_fin),
                "descripcion": o.descripcion,
            })
            cobertura_txt = ", ".join(c.nombre for c in o.ciudades.all()) if o.ciudades.exists() else "Nacional"
            lista_md.append(
                f"🎁 **{o.titulo}** (Periodo: `{o.periodo}`)\n"
                f"- **Vigencia:** Del {o.fecha_inicio} al {o.fecha_fin}\n"
                f"- **Descripción:** {o.descripcion}\n"
                f"- **Cobertura:** {cobertura_txt}"
            )

        texto_md = (
            f"### ⚡ Ofertas Comerciales Vigentes ({periodo_actual})\n\n"
            f"Actualmente se encuentran activas las siguientes ofertas para tu cobertura:\n\n"
            + "\n\n".join(lista_md) +
            "\n\n*Recuerda que solo los vendedores en estado ACTIVO pueden comercializar estas promociones.*"
        )
        return {
            "datos": {
                "tipo": "catalogo_vigente",
                "periodo": periodo_actual,
                "ofertas": ofertas_datos,
            },
            "texto_markdown": texto_md,
        }


# ============================================================================
# ORQUESTACIÓN DE GEMINI CON FUNCTION CALLING NATIVO Y CONTINGENCIA LOCAL
# ============================================================================

async def consultar_gemini(
    prompt: str,
    system_instruction: str = "",
    contexto_negocio: str = "",
    perfil_actor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Invoca a Google Gemini (gemini-3.5-flash-lite) con soporte nativo de Function Calling (Tools).
    Si Gemini detecta una intención operativa, dispara un functionCall, el backend ejecuta la consulta
    con aislamiento por rol sobre la BD, y Gemini sintetiza la respuesta final en lenguaje natural.
    Si no hay API key o hay error de conexión/cuota, aplica el despachador de contingencia local.
    """
    api_key = config("GEMINI_API_KEY", default=None)
    start_time = time.perf_counter()

    if not api_key:
        return await sync_to_async(_generar_respuesta_fallback)(
            prompt,
            motivo="GEMINI_API_KEY no configurada. Operando en modo local asistido.",
            latencia_ms=int((time.perf_counter() - start_time) * 1000),
            perfil_actor=perfil_actor,
        )

    url = f"{GEMINI_API_URL}?key={api_key}"
    headers = {"Content-Type": "application/json"}

    # Ajuste adaptativo de temperatura: mayor libertad analítica/creativa para consejos y coaching comercial
    prompt_lower = prompt.lower()
    es_pedido_consejo = any(
        kw in prompt_lower
        for kw in ["consejo", "recomiend", "recomendar", "mejorar", "desempeño", "estrategia", "tip", "capacit", "motivar", "ayudar"]
    )
    temperatura = 0.55 if es_pedido_consejo else 0.2

    # Turno 1: Enviar prompt con catálogo de herramientas declaradas
    payload_t1: dict[str, Any] = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "tools": GEMINI_TOOLS,
        "generationConfig": {
            "temperature": temperatura,
            "maxOutputTokens": MAX_OUTPUT_TOKENS,
        },
    }
    if system_instruction:
        payload_t1["systemInstruction"] = {"parts": [{"text": system_instruction}]}

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            resp_t1 = await client.post(url, json=payload_t1, headers=headers)
            latencia_t1 = int((time.perf_counter() - start_time) * 1000)

            if resp_t1.status_code == 200:
                data_t1 = resp_t1.json()
                candidate_t1 = data_t1.get("candidates", [{}])[0]
                content_t1 = candidate_t1.get("content", {})
                parts_t1 = content_t1.get("parts", [{}])

                # Identificar si Gemini disparó una herramienta (Function Calling)
                fn_call = None
                for p in parts_t1:
                    if "functionCall" in p:
                        fn_call = p["functionCall"]
                        break

                if fn_call:
                    fn_name = fn_call.get("name")
                    fn_args = fn_call.get("args", {})

                    # Ejecutar la función de dominio solicitada por el modelo
                    if fn_name == "consultar_vendedores":
                        tool_res = await sync_to_async(ejecutar_consulta_vendedores)(
                            estado=fn_args.get("estado", "bloqueado"),
                            perfil_actor=perfil_actor,
                        )
                    elif fn_name == "consultar_metas":
                        tool_res = await sync_to_async(ejecutar_consulta_metas)(
                            periodo=fn_args.get("periodo"),
                            perfil_actor=perfil_actor,
                        )
                    elif fn_name == "consultar_ofertas":
                        tool_res = await sync_to_async(ejecutar_consulta_ofertas)(
                            accion=fn_args.get("accion", "vigentes"),
                            perfil_actor=perfil_actor,
                        )
                    else:
                        tool_res = {"datos": {}, "texto_markdown": ""}

                    # Turno 2: Devolver el resultado de la herramienta a Gemini para síntesis
                    payload_t2 = {
                        "contents": [
                            {"role": "user", "parts": [{"text": prompt}]},
                            content_t1,  # Preserva thoughtSignature exigido en v1beta
                            {
                                "role": "user",
                                "parts": [
                                    {
                                        "functionResponse": {
                                            "name": fn_name,
                                            "response": tool_res.get("datos", {}),
                                        }
                                    }
                                ],
                            },
                        ],
                        "tools": GEMINI_TOOLS,
                        "generationConfig": {
                            "temperature": temperatura,
                            "maxOutputTokens": MAX_OUTPUT_TOKENS,
                        },
                    }
                    if system_instruction:
                        payload_t2["systemInstruction"] = {"parts": [{"text": system_instruction}]}

                    resp_t2 = await client.post(url, json=payload_t2, headers=headers)
                    latencia_total = int((time.perf_counter() - start_time) * 1000)

                    if resp_t2.status_code == 200:
                        data_t2 = resp_t2.json()
                        parts_t2 = data_t2.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                        texto_sintetizado = "\n\n".join(p.get("text", "") for p in parts_t2 if p.get("text")).strip()
                        if not texto_sintetizado:
                            texto_sintetizado = tool_res.get("texto_markdown", "")

                        usage = data_t2.get("usageMetadata", {})
                        tokens_total = usage.get("totalTokenCount", len(prompt) // 4 + 150)

                        resp_payload = {
                            "texto_markdown": texto_sintetizado,
                            "datos_herramienta": tool_res.get("datos"),
                        }
                        if isinstance(tool_res.get("datos"), dict):
                            if "titulo_sugerido" in tool_res["datos"]:
                                resp_payload["titulo_sugerido"] = tool_res["datos"]["titulo_sugerido"]
                            if "descripcion_comercial" in tool_res["datos"]:
                                resp_payload["descripcion_comercial"] = tool_res["datos"]["descripcion_comercial"]

                        return {
                            "ok": True,
                            "modo": "GEMINI_ONLINE",
                            "modelo": GEMINI_MODEL,
                            "herramienta": fn_name,
                            "respuesta": resp_payload,
                            "latencia_ms": latencia_total,
                            "tokens_estimados": tokens_total,
                        }
                    else:
                        # Si falla el turno 2, devolver de inmediato los datos renderizados por la herramienta
                        resp_fallback = {
                            "texto_markdown": tool_res.get("texto_markdown", ""),
                            "datos_herramienta": tool_res.get("datos"),
                        }
                        if isinstance(tool_res.get("datos"), dict):
                            if "titulo_sugerido" in tool_res["datos"]:
                                resp_fallback["titulo_sugerido"] = tool_res["datos"]["titulo_sugerido"]
                            if "descripcion_comercial" in tool_res["datos"]:
                                resp_fallback["descripcion_comercial"] = tool_res["datos"]["descripcion_comercial"]

                        return {
                            "ok": True,
                            "modo": "GEMINI_ONLINE",
                            "modelo": GEMINI_MODEL,
                            "herramienta": fn_name,
                            "respuesta": resp_fallback,
                            "latencia_ms": latencia_total,
                            "tokens_estimados": 0,
                        }

                # Respuesta directa en texto de Gemini (sin llamada a herramientas)
                texto_directo = "\n\n".join(p.get("text", "") for p in parts_t1 if p.get("text")).strip()
                usage = data_t1.get("usageMetadata", {})
                tokens_total = usage.get("totalTokenCount", len(prompt) // 4 + 50)

                return {
                    "ok": True,
                    "modo": "GEMINI_ONLINE",
                    "modelo": GEMINI_MODEL,
                    "respuesta": {
                        "texto_markdown": texto_directo,
                    },
                    "latencia_ms": latencia_t1,
                    "tokens_estimados": tokens_total,
                }

            elif resp_t1.status_code == 429:
                return await sync_to_async(_generar_respuesta_fallback)(
                    prompt,
                    motivo="Cuota temporal de Gemini agotada (HTTP 429). Modo de contingencia activo.",
                    latencia_ms=latencia_t1,
                    perfil_actor=perfil_actor,
                )
            else:
                return await sync_to_async(_generar_respuesta_fallback)(
                    prompt,
                    motivo=f"Respuesta de contingencia (HTTP {resp_t1.status_code}).",
                    latencia_ms=latencia_t1,
                    perfil_actor=perfil_actor,
                )

    except Exception as e:
        latencia_ms = int((time.perf_counter() - start_time) * 1000)
        return await sync_to_async(_generar_respuesta_fallback)(
            prompt,
            motivo=f"Fallo de conexión externa ({type(e).__name__}). Modo de contingencia activo.",
            latencia_ms=latencia_ms,
            perfil_actor=perfil_actor,
        )


def _generar_respuesta_fallback(
    prompt: str,
    motivo: str,
    latencia_ms: int = 50,
    perfil_actor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Despachador determinístico de contingencia local.
    Reutiliza directamente las mismas funciones de dominio sin duplicar lógica ORM.
    NO consume tokens de API de Google (tokens_estimados = 0).
    """
    prompt_clean = prompt.strip().lower()

    # Expresiones regulares de clasificación de intención
    patron_bloqueo = r"\b(bloqu\w*|sancion\w*|vetad\w*|castig\w*)\b"
    patron_inactivo = r"\b(inactiv\w*|desactiv\w*|pausad\w*|cesad\w*|baja\w*)\b|dados?\s+de\s+baja"
    patron_no_activo = r"\bno\s+activ\w*\b|\bfuera\s+de\s+(servicio|l[ií]nea|operaci[oó]n)\b"
    patron_metas = r"\b(meta\w*|cumpli\w*|porcentaj\w*|brecha\w*|avance\w*|logro\w*|indicador\w*|ventas?)\b"
    patron_redactar_oferta = r"\b(redact\w*|crear|diseñ\w*|suger\w*|propon\w*|recomend\w*|copy|nueva\s+oferta)\b"
    patron_ofertas_consulta = r"\b(ofert\w*|promo\w*|promoci[oó]n\w*|paquet\w*|planes)\b"

    if re.search(patron_bloqueo, prompt_clean) or re.search(patron_inactivo, prompt_clean) or re.search(patron_no_activo, prompt_clean):
        if re.search(patron_inactivo, prompt_clean) and not re.search(patron_bloqueo, prompt_clean):
            estado = "inactivo"
        elif re.search(patron_no_activo, prompt_clean):
            estado = "no_activos"
        else:
            estado = "bloqueado"

        tool_res = ejecutar_consulta_vendedores(estado=estado, perfil_actor=perfil_actor)
        return {
            "ok": True,
            "modo": "FALLBACK_LOCAL",
            "modelo": "reglas-contingencia-v1",
            "respuesta": {
                "respuesta_asistente": tool_res["texto_markdown"],
                "texto_markdown": tool_res["texto_markdown"],
                "nota_contingencia": motivo,
            },
            "latencia_ms": latencia_ms,
            "tokens_estimados": 0,
        }

    if re.search(patron_metas, prompt_clean):
        tool_res = ejecutar_consulta_metas(periodo="actual", perfil_actor=perfil_actor)
        return {
            "ok": True,
            "modo": "FALLBACK_LOCAL",
            "modelo": "reglas-contingencia-v1",
            "respuesta": {
                "diagnostico_general": tool_res["datos"].get("porcentaje_cumplimiento"),
                "texto_markdown": tool_res["texto_markdown"],
                "nota_contingencia": motivo,
            },
            "latencia_ms": latencia_ms,
            "tokens_estimados": 0,
        }

    if re.search(patron_redactar_oferta, prompt_clean):
        tool_res = ejecutar_consulta_ofertas(accion="redactar_nueva", perfil_actor=perfil_actor)
        return {
            "ok": True,
            "modo": "FALLBACK_LOCAL",
            "modelo": "reglas-contingencia-v1",
            "respuesta": {
                "titulo_sugerido": tool_res["datos"].get("titulo_sugerido"),
                "descripcion_comercial": tool_res["datos"].get("descripcion"),
                "puntos_clave": tool_res["datos"].get("puntos_clave", []),
                "texto_markdown": tool_res["texto_markdown"],
                "nota_contingencia": motivo,
            },
            "latencia_ms": latencia_ms,
            "tokens_estimados": 0,
        }

    if re.search(patron_ofertas_consulta, prompt_clean):
        tool_res = ejecutar_consulta_ofertas(accion="vigentes", perfil_actor=perfil_actor)
        return {
            "ok": True,
            "modo": "FALLBACK_LOCAL",
            "modelo": "reglas-contingencia-v1",
            "respuesta": {
                "texto_markdown": tool_res["texto_markdown"],
                "nota_contingencia": motivo,
            },
            "latencia_ms": latencia_ms,
            "tokens_estimados": 0,
        }

    texto_general = (
        "¡Hola! Soy tu Copiloto comercial de VERLA SAS. Conozco el estado de la red comercial, "
        "las metas mensuales, los vendedores bloqueados/inactivos y las ofertas vigentes. "
        "¿En qué te puedo colaborar hoy? Puedes consultarme:\n\n"
        "- *¿Qué vendedores están bloqueados o inactivos?*\n"
        "- *¿Cómo va el cumplimiento de metas y cuál es el porcentaje alcanzado?*\n"
        "- *¿Qué ofertas comerciales tenemos vigentes en el periodo?*\n"
        "- *Recomiéndame y redacta una nueva oferta comercial.*"
    )
    return {
        "ok": True,
        "modo": "FALLBACK_LOCAL",
        "modelo": "reglas-contingencia-v1",
        "respuesta": {
            "respuesta_asistente": texto_general,
            "texto_markdown": texto_general,
            "nota_contingencia": motivo,
        },
        "latencia_ms": latencia_ms,
        "tokens_estimados": 0,
    }


def registrar_auditoria_ia(
    usuario: Any,
    caso_uso: str,
    prompt: str,
    resultado: dict[str, Any],
    decision: str = DecisionHumanaIA.PENDIENTE,
) -> AIAuditLog:
    """Registra la invocación y telemetría en AIAuditLog asegurando trazabilidad y gobernanza."""
    return AIAuditLog.objects.create(
        usuario=usuario if getattr(usuario, "is_authenticated", False) else None,
        caso_uso=caso_uso,
        modelo=resultado.get("modelo", GEMINI_MODEL),
        prompt_resumen=prompt[:500],
        respuesta_json=resultado.get("respuesta", {}),
        latencia_ms=resultado.get("latencia_ms", 0),
        tokens_estimados=resultado.get("tokens_estimados", 0),
        decision_humana=decision,
    )
