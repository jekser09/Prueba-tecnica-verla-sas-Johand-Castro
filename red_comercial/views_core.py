from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from red_comercial.models import Aliado, Ciudad, Coordinador, EstadoVendedor, Vendedor

User = get_user_model()


def home_view(request: HttpRequest) -> HttpResponse:
    """Vista principal / landing del portal con accesos rápidos."""
    return render(request, "core/home.html")


def _obtener_o_crear_usuario_demo(username: str, email: str, is_staff: bool = False, is_superuser: bool = False) -> Any:
    user, created = User.objects.get_or_create(
        username=username,
        defaults={
            "email": email,
            "first_name": username.capitalize(),
            "is_staff": is_staff,
            "is_superuser": is_superuser,
        },
    )
    if created:
        user.set_password("demo123456")
        user.save()
    return user


@require_POST
def simular_rol_view(request: HttpRequest) -> HttpResponseRedirect:
    """
    Controlador para cambiar ágilmente el usuario autenticado durante la demostración técnica.
    Crea o reutiliza entidades y usuarios representativos para cada rol del sistema.
    Redirige siempre a la página principal (/) para evitar colisiones de rutas no autorizadas.
    """
    rol_solicitado = request.POST.get("rol_simulado", "admin")
    next_url = "/"

    # Ciudad demo de soporte
    ciudad_demo = Ciudad.objects.first()
    if not ciudad_demo:
        ciudad_demo = Ciudad.objects.create(
            codigo="BOG",
            nombre="Bogotá D.C.",
            departamento="Cundinamarca",
            activa=True,
        )

    # 1. Coordinador demo: Carlos Mendoza (CC-COORD-001) o el primero con vendedores asignados
    coord_demo = Coordinador.objects.filter(documento="CC-COORD-001").first()
    if not coord_demo:
        coord_demo = Coordinador.objects.filter(vendedores__isnull=False).distinct().first()

    # 2. Aliado demo: el aliado asignado al coordinador demo, o Distribuciones Andinas SAS, o el primero existente
    if coord_demo and coord_demo.aliado:
        aliado_demo = coord_demo.aliado
    else:
        aliado_demo = Aliado.objects.filter(nit="900100101-1").first() or Aliado.objects.first()

    if not aliado_demo:
        aliado_demo = Aliado.objects.create(
            nit="900100101-1",
            razon_social="[TEST] Distribuciones Andinas SAS",
            codigo_contrato="CTR-AND-01",
            correo_contacto="contacto@andina.com",
            telefono="3101234567",
            activo=True,
        )

    if not coord_demo:
        coord_demo, _ = Coordinador.objects.get_or_create(
            documento="CC-COORD-001",
            defaults={
                "aliado": aliado_demo,
                "nombre_completo": "[TEST] Carlos Mendoza Coordinador",
                "correo": "carlos.mendoza@andina.com",
                "telefono": "3119876543",
                "activo": True,
            },
        )
    if coord_demo.aliado != aliado_demo:
        coord_demo.aliado = aliado_demo
        coord_demo.save()

    if rol_solicitado == "admin":
        user = _obtener_o_crear_usuario_demo("demo_admin", "admin@verla.com.co", is_staff=True, is_superuser=True)

    elif rol_solicitado == "aliado":
        user = _obtener_o_crear_usuario_demo("demo_aliado", "aliado@andina.com")
        Aliado.objects.filter(usuario=user).exclude(pk=aliado_demo.pk).update(usuario=None)
        if aliado_demo.usuario != user:
            aliado_demo.usuario = user
            aliado_demo.save()

    elif rol_solicitado == "coordinador":
        user = _obtener_o_crear_usuario_demo("demo_coordinador", "coord@andina.com")
        Coordinador.objects.filter(usuario=user).exclude(pk=coord_demo.pk).update(usuario=None)
        if coord_demo.usuario != user:
            coord_demo.usuario = user
            coord_demo.save()

    elif rol_solicitado == "vendedor_activo":
        user = _obtener_o_crear_usuario_demo("demo_vendedor_activo", "vendedor.activo@andina.com")
        vendedor_activo = Vendedor.objects.filter(documento="CC-VEND-ACTIVO").first()
        if not vendedor_activo:
            vendedor_activo = Vendedor.objects.create(
                documento="CC-VEND-ACTIVO",
                coordinador=coord_demo,
                nombre_completo="[TEST] Laura Gómez Vendedora",
                correo="laura.gomez@andina.com",
                telefono="3201112233",
                cargo="Asesor Comercial Senior",
                ciudad_base=ciudad_demo,
                estado=EstadoVendedor.ACTIVO,
                fecha_ingreso=timezone.now().date(),
                usuario=user,
            )
        Vendedor.objects.filter(usuario=user).exclude(pk=vendedor_activo.pk).update(usuario=None)
        if vendedor_activo.usuario != user or vendedor_activo.estado != EstadoVendedor.ACTIVO:
            vendedor_activo.usuario = user
            vendedor_activo.estado = EstadoVendedor.ACTIVO
            vendedor_activo.save()

    elif rol_solicitado == "vendedor_bloqueado":
        user = _obtener_o_crear_usuario_demo("demo_vendedor_bloqueado", "vendedor.bloqueado@andina.com")
        vendedor_bloqueado = Vendedor.objects.filter(documento="CC-VEND-BLOQUEADO").first()
        if not vendedor_bloqueado:
            vendedor_bloqueado = Vendedor.objects.create(
                documento="CC-VEND-BLOQUEADO",
                coordinador=coord_demo,
                nombre_completo="[TEST] Pedro Restrepo Bloqueado",
                correo="pedro.restrepo@andina.com",
                telefono="3209998877",
                cargo="Asesor Comercial Junior",
                ciudad_base=ciudad_demo,
                estado=EstadoVendedor.BLOQUEADO,
                motivo_estado="Incumplimiento de políticas comerciales de cobranza.",
                fecha_ingreso=timezone.now().date(),
                usuario=user,
            )
        Vendedor.objects.filter(usuario=user).exclude(pk=vendedor_bloqueado.pk).update(usuario=None)
        if vendedor_bloqueado.usuario != user or vendedor_bloqueado.estado != EstadoVendedor.BLOQUEADO:
            vendedor_bloqueado.usuario = user
            vendedor_bloqueado.estado = EstadoVendedor.BLOQUEADO
            vendedor_bloqueado.motivo_estado = "Incumplimiento de políticas comerciales de cobranza."
            vendedor_bloqueado.save()
    else:
        user = _obtener_o_crear_usuario_demo("demo_admin", "admin@verla.com.co", is_staff=True, is_superuser=True)

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    messages.success(request, f"Rol simulado activo: {rol_solicitado.upper()} (Usuario: {user.username})")
    return redirect(next_url)
