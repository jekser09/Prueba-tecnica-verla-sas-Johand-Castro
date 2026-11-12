from __future__ import annotations

from typing import Any

from django.http import HttpRequest
from red_comercial.rbac import obtener_perfil_actor


def portal_context(request: HttpRequest) -> dict[str, Any]:
    """
    Inyecta el perfil de actor (rol, objetos asociados, bloqueos) y la información
    de marca de VERLA SAS a todos los templates del portal.
    """
    actor = obtener_perfil_actor(request.user)
    return {
        "actor": actor,
        "PORTAL_TITLE": "Portal de Aliados Comerciales — VERLA SAS",
    }
