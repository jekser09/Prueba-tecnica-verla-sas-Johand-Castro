from __future__ import annotations

import json
import time
from typing import Any

from decouple import config
import httpx
from django.utils import timezone

from asistente_ia.models import AIAuditLog, CasoUsoIA, DecisionHumanaIA


GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"


async def consultar_gemini(prompt: str, system_instruction: str = "") -> dict[str, Any]:
    """
    Invoca de forma asíncrona a la API de Google Gemini (gemini-2.5-flash).
    Si no hay GEMINI_API_KEY, si hay error de red o HTTP 429, retorna una respuesta
    estructurada de fallback garantizando disponibilidad sin caídas.
    """
    api_key = config("GEMINI_API_KEY", default=None)
    start_time = time.perf_counter()

    if not api_key:
        return _generar_respuesta_fallback(
            prompt,
            motivo="GEMINI_API_KEY no configurada. Operando en modo local asistido.",
            latencia_ms=int((time.perf_counter() - start_time) * 1000),
        )

    url = f"{GEMINI_API_URL}?key={api_key}"
    payload: dict[str, Any] = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "responseMimeType": "application/json",
        },
    }
    if system_instruction:
        payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

    headers = {"Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            latencia_ms = int((time.perf_counter() - start_time) * 1000)

            if response.status_code == 200:
                data = response.json()
                texto_raw = (
                    data.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "{}")
                )
                try:
                    parsed_json = json.loads(texto_raw)
                except json.JSONDecodeError:
                    parsed_json = {"texto_directo": texto_raw}

                usage = data.get("usageMetadata", {})
                tokens_total = usage.get("totalTokenCount", len(prompt) // 4 + 100)

                return {
                    "ok": True,
                    "modo": "GEMINI_ONLINE",
                    "modelo": "gemini-2.5-flash",
                    "respuesta": parsed_json,
                    "latencia_ms": latencia_ms,
                    "tokens_estimados": tokens_total,
                }

            elif response.status_code == 429:
                return _generar_respuesta_fallback(
                    prompt,
                    motivo="Cuota temporal de Gemini agotada (HTTP 429). Se activó el generador de contingencia.",
                    latencia_ms=latencia_ms,
                )
            else:
                return _generar_respuesta_fallback(
                    prompt,
                    motivo=f"Respuesta inesperada de Google API (HTTP {response.status_code}). Modo de contingencia activo.",
                    latencia_ms=latencia_ms,
                )

    except Exception as e:
        latencia_ms = int((time.perf_counter() - start_time) * 1000)
        return _generar_respuesta_fallback(
            prompt,
            motivo=f"Fallo de conexión externa ({type(e).__name__}). Modo de contingencia activo.",
            latencia_ms=latencia_ms,
        )


def _generar_respuesta_fallback(prompt: str, motivo: str, latencia_ms: int = 50) -> dict[str, Any]:
    """Genera respuestas determinísticas inteligentes y realistas cuando la API externa no está disponible."""
    prompt_lower = prompt.lower()

    if "oferta" in prompt_lower or "copy" in prompt_lower or "redactar" in prompt_lower:
        respuesta = {
            "titulo_sugerido": "Super Promo Fibra Óptica 300MB + TV Pro",
            "descripcion_comercial": (
                "¡Impulsa tu conectividad con VERLA SAS! Obtén 300 Megas simétricas con instalación preferencial "
                "y 3 meses al 20% de descuento para clientes residenciales y comerciales activos."
            ),
            "puntos_clave": [
                "Velocidad 100% simétrica con soporte prioritario 24/7.",
                "Instalación en menos de 48 horas hábiles en ciudades autorizadas.",
                "Comisión comercial acelerada para asesores de la red.",
            ],
            "nota_contingencia": motivo,
        }
    elif "meta" in prompt_lower or "brecha" in prompt_lower or "analisis" in prompt_lower:
        respuesta = {
            "diagnostico_general": "El cumplimiento global del periodo se encuentra en rango de supervisión moderada.",
            "alertas_criticas": [
                "Vendedores con cumplimiento inferior al 80% requieren revisión de ruta y acompañamiento en terreno.",
            ],
            "plan_de_accion": [
                "Reforzar el portafolio de ofertas activas del mes en ciudades con rezago de venta.",
                "Programar comités de seguimiento comercial semanales entre Coordinadores y asesores.",
                "Priorizar clientes con oportunidad de up-selling en fibra de mayor velocidad.",
            ],
            "nota_contingencia": motivo,
        }
    else:
        respuesta = {
            "respuesta_asistente": (
                "Hola, soy el copiloto de VERLA SAS. Puedo ayudarte a redactar copys de ofertas comerciales "
                "o analizar el cumplimiento de metas del periodo. ¿Sobre qué área deseas apoyo hoy?"
            ),
            "nota_contingencia": motivo,
        }

    return {
        "ok": True,
        "modo": "FALLBACK_LOCAL",
        "modelo": "reglas-contingencia-v1",
        "respuesta": respuesta,
        "latencia_ms": latencia_ms,
        "tokens_estimados": 120,
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
        modelo=resultado.get("modelo", "gemini-2.5-flash"),
        prompt_resumen=prompt[:500],
        respuesta_json=resultado.get("respuesta", {}),
        latencia_ms=resultado.get("latencia_ms", 0),
        tokens_estimados=resultado.get("tokens_estimados", 0),
        decision_humana=decision,
    )
