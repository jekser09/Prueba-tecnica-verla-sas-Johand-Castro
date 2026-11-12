from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from red_comercial.models import EstadoVendedor, Vendedor


def obtener_perfil_actor(user: Any) -> dict[str, Any]:
    """
    Inspecciona el usuario autenticado y retorna un diccionario descriptivo con su
    rol asignado, perfil asociado y estado operativo si es Vendedor.
    """
    if not getattr(user, "is_authenticated", False):
        return {
            "rol": "ANONIMO",
            "es_admin": False,
            "es_aliado": False,
            "es_coordinador": False,
            "es_vendedor": False,
            "objeto": None,
            "bloqueado": False,
            "inactivo": False,
            "estado_vendedor": None,
        }

    if user.is_superuser or user.is_staff:
        return {
            "rol": "ADMIN",
            "es_admin": True,
            "es_aliado": False,
            "es_coordinador": False,
            "es_vendedor": False,
            "objeto": None,
            "bloqueado": False,
            "inactivo": False,
            "estado_vendedor": None,
        }

    if hasattr(user, "perfil_aliado") and user.perfil_aliado:
        return {
            "rol": "ALIADO",
            "es_admin": False,
            "es_aliado": True,
            "es_coordinador": False,
            "es_vendedor": False,
            "objeto": user.perfil_aliado,
            "bloqueado": not user.perfil_aliado.activo,
            "inactivo": not user.perfil_aliado.activo,
            "estado_vendedor": None,
        }

    if hasattr(user, "perfil_coordinador") and user.perfil_coordinador:
        return {
            "rol": "COORDINADOR",
            "es_admin": False,
            "es_aliado": False,
            "es_coordinador": True,
            "es_vendedor": False,
            "objeto": user.perfil_coordinador,
            "bloqueado": not user.perfil_coordinador.activo,
            "inactivo": not user.perfil_coordinador.activo,
            "estado_vendedor": None,
        }

    if hasattr(user, "perfil_vendedor") and user.perfil_vendedor:
        vendedor: Vendedor = user.perfil_vendedor
        es_bloqueado = vendedor.estado == EstadoVendedor.BLOQUEADO
        es_inactivo = vendedor.estado == EstadoVendedor.INACTIVO
        return {
            "rol": "VENDEDOR",
            "es_admin": False,
            "es_aliado": False,
            "es_coordinador": False,
            "es_vendedor": True,
            "objeto": vendedor,
            "bloqueado": es_bloqueado,
            "inactivo": es_inactivo,
            "estado_vendedor": vendedor.estado,
        }

    return {
        "rol": "USUARIO",
        "es_admin": False,
        "es_aliado": False,
        "es_coordinador": False,
        "es_vendedor": False,
        "objeto": None,
        "bloqueado": False,
        "inactivo": False,
        "estado_vendedor": None,
    }


def verificar_vendedor_operativo(request: HttpRequest) -> HttpResponse | None:
    """
    Verifica si el usuario es un vendedor y si su estado es BLOQUEADO o INACTIVO.
    Si está restringido, renderiza la pantalla de bloqueo o advertencia operativa con HTTP 403.
    """
    perfil = obtener_perfil_actor(request.user)
    if perfil["es_vendedor"]:
        if perfil["bloqueado"]:
            return render(
                request,
                "core/acceso_bloqueado.html",
                {
                    "titulo": "Acceso Comercial Bloqueado",
                    "mensaje": "Su usuario de vendedor se encuentra actualmente BLOQUEADO para operaciones comerciales. Motivo: "
                    + (perfil["objeto"].motivo_estado or "Restricción administrativa activa."),
                    "estado": EstadoVendedor.BLOQUEADO,
                },
                status=403,
            )
        if perfil["inactivo"]:
            return render(
                request,
                "core/acceso_bloqueado.html",
                {
                    "titulo": "Cuenta de Vendedor Inactiva",
                    "mensaje": "Su ficha comercial se encuentra INACTIVA. Contacte a su Coordinador comercial o Aliado.",
                    "estado": EstadoVendedor.INACTIVO,
                },
                status=403,
            )
    return None


def requerir_roles(*roles_permitidos: str) -> Callable:
    """
    Decorador de vista para asegurar autenticación, verificar roles permitidos
    y restringir operaciones cuando el vendedor está BLOQUEADO o INACTIVO.
    """
    def decorador(view_func: Callable) -> Callable:
        @wraps(view_func)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            if not request.user.is_authenticated:
                return redirect(f"/login/?next={request.path}")

            # Revisión de bloqueo para vendedores
            bloqueo_response = verificar_vendedor_operativo(request)
            if bloqueo_response:
                return bloqueo_response

            perfil = obtener_perfil_actor(request.user)
            if "ADMIN" in roles_permitidos and (request.user.is_superuser or request.user.is_staff):
                return view_func(request, *args, **kwargs)

            if perfil["rol"] not in roles_permitidos:
                # Si el usuario es un vendedor bloqueado, verificar_vendedor_operativo ya lo interceptó arriba.
                # Para otros roles no autorizados, solo registramos mensaje si no es un vendedor bloqueado
                if not (perfil["es_vendedor"] and perfil["bloqueado"]):
                    messages.error(
                        request,
                        f"No tiene permisos para realizar esta acción. Su rol activo ({perfil['rol']}) no cuenta con autorización."
                    )

                # Si el usuario intentó acceder a una acción específica (ej. editar o crear) y viene de una vista interna,
                # redirigir a la vista previa para no expulsarlo al inicio.
                referer = request.META.get("HTTP_REFERER")
                if referer:
                    from urllib.parse import urlparse
                    ref_url = urlparse(referer)
                    curr_host = request.get_host()
                    if not ref_url.netloc or ref_url.netloc == curr_host:
                        return redirect(referer)

                # Si no hay referer, verificar si el rol tiene acceso a la vista de lista del submódulo
                path = request.path
                if "/vendedores/" in path and (perfil["es_admin"] or perfil["es_aliado"] or perfil["es_coordinador"]):
                    return redirect("vendedor_list")
                if "/coordinadores/" in path and (perfil["es_admin"] or perfil["es_aliado"] or perfil["es_coordinador"]):
                    return redirect("coordinador_list")
                if "/aliados/" in path and (perfil["es_admin"] or perfil["es_aliado"] or perfil["es_coordinador"]):
                    return redirect("aliado_list")
                if "/ciudades/" in path and (perfil["es_admin"] or perfil["es_aliado"] or perfil["es_coordinador"]):
                    return redirect("ciudad_list")
                if "/operacion/" in path and (perfil["es_admin"] or perfil["es_aliado"] or perfil["es_coordinador"]):
                    return redirect("op_default")

                # Solo cuando el rol no tiene acceso a la vista completa del módulo, redirigir al inicio o su portal
                if perfil["es_vendedor"]:
                    return redirect("op_default")
                return redirect("portal_home")

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorador
