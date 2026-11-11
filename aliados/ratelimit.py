"""
Middleware de limitación de tasa (Rate Limiting) compatible con WSGI y ASGI.

Protege las rutas generales del portal y aplica una cuota estricta al módulo
de inteligencia artificial (/asistente/) para resguardar el presupuesto de
la API de Google Gemini contra ráfagas o abuso automatizado.
"""

from __future__ import annotations

import time
from typing import Callable

from asgiref.sync import iscoroutinefunction
from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils.decorators import sync_and_async_middleware

# Mensaje estándar en español neutral cuando se supera el umbral de solicitudes por ventana.
RATE_LIMIT_ERROR_MESSAGE = "Demasiadas solicitudes. Por favor espere antes de intentar nuevamente."


def _get_client_ip(request: HttpRequest) -> str:
    """
    Obtiene la dirección IP del cliente inspeccionando primero X-Forwarded-For
    (en caso de operar detrás de un proxy inverso) y luego REMOTE_ADDR.
    """
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or "127.0.0.1"


def _is_exempt_path(path: str) -> bool:
    """
    Exime del conteo de límite de tasa a las rutas de archivos estáticos y multimedia.
    """
    static_url = getattr(settings, "STATIC_URL", "/static/") or "/static/"
    media_url = getattr(settings, "MEDIA_URL", "/media/") or "/media/"
    return path.startswith(static_url) or path.startswith(media_url)


def _resolve_scope_and_limit(path: str) -> tuple[str, int]:
    """
    Determina el ámbito ('ai' o 'global') y el límite máximo de solicitudes por ventana
    según el prefijo de la ruta solicitada.
    """
    if path.startswith("/asistente/"):
        limit = int(getattr(settings, "RATE_LIMIT_AI_REQUESTS", 10))
        return "ai", limit
    limit = int(getattr(settings, "RATE_LIMIT_GLOBAL_REQUESTS", 120))
    return "global", limit


def _wants_json_response(request: HttpRequest) -> bool:
    """
    Determina si la respuesta de bloqueo 429 debe entregarse en formato JSON
    (para llamadas al módulo de IA, peticiones AJAX/fetch o cabeceras Accept JSON).
    """
    if request.path.startswith("/asistente/") or request.path.startswith("/api/"):
        return True
    accept = request.headers.get("Accept", "")
    requested_with = request.headers.get("X-Requested-With", "")
    return "application/json" in accept or requested_with == "XMLHttpRequest"


def _evaluate_rate_limit(request: HttpRequest) -> tuple[bool, int, int, int]:
    """
    Evalúa y actualiza el contador de ventana fija en la caché de Django.

    Retorna una tupla (allowed, limit, remaining, retry_after).
    """
    window_seconds = max(1, int(getattr(settings, "RATE_LIMIT_WINDOW_SECONDS", 60)))
    scope, limit = _resolve_scope_and_limit(request.path)
    client_ip = _get_client_ip(request)

    now = int(time.time())
    window_bucket = now // window_seconds
    retry_after = max(1, window_seconds - (now % window_seconds))
    cache_key = f"ratelimit:{scope}:{client_ip}:{window_bucket}"

    # Si la clave no existe en la ventana actual, se inicializa atómicamente en 1.
    added = cache.add(cache_key, 1, timeout=window_seconds)
    if added:
        current_count = 1
    else:
        try:
            current_count = cache.incr(cache_key)
        except ValueError:
            cache.set(cache_key, 1, timeout=window_seconds)
            current_count = 1

    allowed = current_count <= limit
    remaining = max(0, limit - current_count)
    return allowed, limit, remaining, retry_after


def _attach_rate_limit_headers(
    response: HttpResponse,
    limit: int,
    remaining: int,
    retry_after: int | None = None,
) -> HttpResponse:
    """
    Adjunta las cabeceras informativas de cuota a la respuesta HTTP.
    """
    response["X-RateLimit-Limit"] = str(limit)
    response["X-RateLimit-Remaining"] = str(remaining)
    if retry_after is not None:
        response["Retry-After"] = str(retry_after)
    return response


def _build_rate_limited_response(
    request: HttpRequest,
    limit: int,
    retry_after: int,
) -> HttpResponse:
    """
    Construye la respuesta HTTP 429 Too Many Requests en JSON o HTML según el cliente.
    """
    if _wants_json_response(request):
        response: HttpResponse = JsonResponse(
            {
                "error": RATE_LIMIT_ERROR_MESSAGE,
                "retry_after": retry_after,
            },
            status=429,
        )
    else:
        html_body = (
            "<!DOCTYPE html>"
            "<html lang=\"es\" data-theme=\"dark\">"
            "<head><meta charset=\"utf-8\"><title>429 Demasiadas solicitudes</title></head>"
            "<body><main class=\"container\">"
            "<h1>429 — Demasiadas solicitudes</h1>"
            f"<p>{RATE_LIMIT_ERROR_MESSAGE}</p>"
            f"<p>Intente nuevamente en {retry_after} segundos.</p>"
            "</main></body></html>"
        )
        response = HttpResponse(
            html_body,
            status=429,
            content_type="text/html; charset=utf-8",
        )

    return _attach_rate_limit_headers(response, limit=limit, remaining=0, retry_after=retry_after)


@sync_and_async_middleware
def RateLimitMiddleware(get_response: Callable):
    """
    Middleware híbrido WSGI/ASGI que aplica control de tasa por IP y ámbito de ruta.
    """
    if iscoroutinefunction(get_response):

        async def async_middleware(request: HttpRequest) -> HttpResponse:
            if not getattr(settings, "RATE_LIMIT_ENABLED", True) or _is_exempt_path(request.path):
                return await get_response(request)

            allowed, limit, remaining, retry_after = _evaluate_rate_limit(request)
            if not allowed:
                return _build_rate_limited_response(request, limit=limit, retry_after=retry_after)

            response = await get_response(request)
            return _attach_rate_limit_headers(response, limit=limit, remaining=remaining)

        return async_middleware

    def sync_middleware(request: HttpRequest) -> HttpResponse:
        if not getattr(settings, "RATE_LIMIT_ENABLED", True) or _is_exempt_path(request.path):
            return get_response(request)

        allowed, limit, remaining, retry_after = _evaluate_rate_limit(request)
        if not allowed:
            return _build_rate_limited_response(request, limit=limit, retry_after=retry_after)

        response = get_response(request)
        return _attach_rate_limit_headers(response, limit=limit, remaining=remaining)

    return sync_middleware
