from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from red_comercial.forms import AliadoForm, CiudadForm, CoordinadorForm, VendedorForm
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
from red_comercial.rbac import requerir_roles


@requerir_roles("ADMIN", "ALIADO", "COORDINADOR")
def red_comercial_dashboard_view(request: HttpRequest) -> HttpResponse:
    """Dashboard general y accesos de administración de la Red Comercial."""
    total_ciudades = Ciudad.objects.count()
    total_aliados = Aliado.objects.count()
    total_coordinadores = Coordinador.objects.count()
    vendedores_activos = Vendedor.objects.filter(estado=EstadoVendedor.ACTIVO).count()
    vendedores_bloqueados = Vendedor.objects.filter(estado=EstadoVendedor.BLOQUEADO).count()

    context = {
        "total_ciudades": total_ciudades,
        "total_aliados": total_aliados,
        "total_coordinadores": total_coordinadores,
        "vendedores_activos": vendedores_activos,
        "vendedores_bloqueados": vendedores_bloqueados,
    }
    return render(request, "red_comercial/dashboard.html", context)


# ==============================================================================
# CRUD CIUDADES
# ==============================================================================

@requerir_roles("ADMIN", "ALIADO")
def ciudad_list_view(request: HttpRequest) -> HttpResponse:
    ciudades = Ciudad.objects.all().order_by("nombre")
    return render(request, "red_comercial/ciudad_list.html", {"ciudades": ciudades})


@requerir_roles("ADMIN")
def ciudad_create_view(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = CiudadForm(request.POST)
        if form.is_valid():
            ciudad = form.save()
            messages.success(request, f"Ciudad '{ciudad.nombre}' creada con éxito.")
            return redirect(reverse("ciudad_list"))
    else:
        form = CiudadForm()
    return render(request, "red_comercial/ciudad_form.html", {"form": form, "titulo": "Nueva Ciudad"})


@requerir_roles("ADMIN")
def ciudad_update_view(request: HttpRequest, pk: int) -> HttpResponse:
    ciudad = get_object_or_404(Ciudad, pk=pk)
    if request.method == "POST":
        form = CiudadForm(request.POST, instance=ciudad)
        expected_version = int(request.POST.get("version", ciudad.version))
        if form.is_valid():
            try:
                ciudad.optimistic_update(
                    expected_version=expected_version,
                    usuario=request.user,
                    accion=AccionAuditoria.ACTUALIZACION,
                    codigo=form.cleaned_data["codigo"],
                    nombre=form.cleaned_data["nombre"],
                    departamento=form.cleaned_data["departamento"],
                    activa=form.cleaned_data["activa"],
                )
                messages.success(request, f"Ciudad '{ciudad.nombre}' actualizada exitosamente.")
                return redirect(reverse("ciudad_list"))
            except ConcurrentModificationError as e:
                ciudad.refresh_from_db()
                form = CiudadForm(instance=ciudad)
                return render(
                    request,
                    "red_comercial/ciudad_form.html",
                    {"form": form, "titulo": f"Editar {ciudad.nombre}", "concurrency_error": str(e), "ciudad": ciudad},
                    status=409,
                )
    else:
        form = CiudadForm(instance=ciudad)
    return render(request, "red_comercial/ciudad_form.html", {"form": form, "titulo": f"Editar {ciudad.nombre}", "ciudad": ciudad})


# ==============================================================================
# CRUD ALIADOS
# ==============================================================================

@requerir_roles("ADMIN", "ALIADO")
def aliado_list_view(request: HttpRequest) -> HttpResponse:
    aliados = Aliado.objects.all().order_by("razon_social")
    return render(request, "red_comercial/aliado_list.html", {"aliados": aliados})


@requerir_roles("ADMIN")
def aliado_create_view(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = AliadoForm(request.POST)
        if form.is_valid():
            aliado = form.save()
            messages.success(request, f"Aliado comercial '{aliado.razon_social}' creado con éxito.")
            return redirect(reverse("aliado_list"))
    else:
        form = AliadoForm()
    return render(request, "red_comercial/aliado_form.html", {"form": form, "titulo": "Nuevo Aliado Comercial"})


@requerir_roles("ADMIN")
def aliado_update_view(request: HttpRequest, pk: int) -> HttpResponse:
    aliado = get_object_or_404(Aliado, pk=pk)
    if request.method == "POST":
        form = AliadoForm(request.POST, instance=aliado)
        expected_version = int(request.POST.get("version", aliado.version))
        if form.is_valid():
            try:
                aliado.optimistic_update(
                    expected_version=expected_version,
                    usuario=request.user,
                    accion=AccionAuditoria.ACTUALIZACION,
                    nit=form.cleaned_data["nit"],
                    razon_social=form.cleaned_data["razon_social"],
                    codigo_contrato=form.cleaned_data["codigo_contrato"],
                    correo_contacto=form.cleaned_data["correo_contacto"],
                    telefono=form.cleaned_data["telefono"],
                    activo=form.cleaned_data["activo"],
                )
                messages.success(request, f"Aliado '{aliado.razon_social}' actualizado exitosamente.")
                return redirect(reverse("aliado_list"))
            except ConcurrentModificationError as e:
                aliado.refresh_from_db()
                form = AliadoForm(instance=aliado)
                return render(
                    request,
                    "red_comercial/aliado_form.html",
                    {"form": form, "titulo": f"Editar {aliado.razon_social}", "concurrency_error": str(e), "aliado": aliado},
                    status=409,
                )
    else:
        form = AliadoForm(instance=aliado)
    return render(request, "red_comercial/aliado_form.html", {"form": form, "titulo": f"Editar {aliado.razon_social}", "aliado": aliado})


# ==============================================================================
# CRUD COORDINADORES
# ==============================================================================

@requerir_roles("ADMIN", "ALIADO", "COORDINADOR")
def coordinador_list_view(request: HttpRequest) -> HttpResponse:
    coordinadores = Coordinador.objects.select_related("aliado").all().order_by("nombre_completo")
    return render(request, "red_comercial/coordinador_list.html", {"coordinadores": coordinadores})


@requerir_roles("ADMIN", "ALIADO")
def coordinador_create_view(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = CoordinadorForm(request.POST)
        if form.is_valid():
            coordinador = form.save()
            messages.success(request, f"Coordinador '{coordinador.nombre_completo}' registrado exitosamente.")
            return redirect(reverse("coordinador_list"))
    else:
        form = CoordinadorForm()
    return render(request, "red_comercial/coordinador_form.html", {"form": form, "titulo": "Nuevo Coordinador"})


@requerir_roles("ADMIN", "ALIADO")
def coordinador_update_view(request: HttpRequest, pk: int) -> HttpResponse:
    coordinador = get_object_or_404(Coordinador, pk=pk)
    if request.method == "POST":
        form = CoordinadorForm(request.POST, instance=coordinador)
        expected_version = int(request.POST.get("version", coordinador.version))
        if form.is_valid():
            try:
                coordinador.optimistic_update(
                    expected_version=expected_version,
                    usuario=request.user,
                    accion=AccionAuditoria.ACTUALIZACION,
                    aliado=form.cleaned_data["aliado"],
                    documento=form.cleaned_data["documento"],
                    nombre_completo=form.cleaned_data["nombre_completo"],
                    correo=form.cleaned_data["correo"],
                    telefono=form.cleaned_data["telefono"],
                    activo=form.cleaned_data["activo"],
                )
                messages.success(request, f"Coordinador '{coordinador.nombre_completo}' actualizado.")
                return redirect(reverse("coordinador_list"))
            except ConcurrentModificationError as e:
                coordinador.refresh_from_db()
                form = CoordinadorForm(instance=coordinador)
                return render(
                    request,
                    "red_comercial/coordinador_form.html",
                    {"form": form, "titulo": f"Editar {coordinador.nombre_completo}", "concurrency_error": str(e), "coordinador": coordinador},
                    status=409,
                )
    else:
        form = CoordinadorForm(instance=coordinador)
    return render(request, "red_comercial/coordinador_form.html", {"form": form, "titulo": f"Editar {coordinador.nombre_completo}", "coordinador": coordinador})


# ==============================================================================
# CRUD VENDEDORES & GOBERNANZA DE ESTADOS
# ==============================================================================

@requerir_roles("ADMIN", "ALIADO", "COORDINADOR")
def vendedor_list_view(request: HttpRequest) -> HttpResponse:
    filtro_estado = request.GET.get("estado", "")
    filtro_q = request.GET.get("q", "").strip()

    vendedores_qs = Vendedor.objects.select_related("aliado", "coordinador", "ciudad_base").prefetch_related("ciudades_operacion").all()

    if filtro_estado:
        vendedores_qs = vendedores_qs.filter(estado=filtro_estado)
    if filtro_q:
        vendedores_qs = vendedores_qs.filter(nombre_completo__icontains=filtro_q) | vendedores_qs.filter(documento__icontains=filtro_q)

    vendedores = vendedores_qs.order_by("nombre_completo")
    return render(
        request,
        "red_comercial/vendedor_list.html",
        {"vendedores": vendedores, "filtro_estado": filtro_estado, "filtro_q": filtro_q, "estados": EstadoVendedor.choices},
    )


@requerir_roles("ADMIN", "ALIADO", "COORDINADOR")
def vendedor_create_view(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = VendedorForm(request.POST)
        if form.is_valid():
            vendedor = form.save()
            messages.success(request, f"Vendedor '{vendedor.nombre_completo}' registrado exitosamente.")
            return redirect(reverse("vendedor_list"))
    else:
        form = VendedorForm()
    return render(request, "red_comercial/vendedor_form.html", {"form": form, "titulo": "Registrar Nuevo Vendedor"})


@requerir_roles("ADMIN", "ALIADO", "COORDINADOR")
def vendedor_update_view(request: HttpRequest, pk: int) -> HttpResponse:
    vendedor = get_object_or_404(Vendedor, pk=pk)
    if request.method == "POST":
        form = VendedorForm(request.POST, instance=vendedor)
        expected_version = int(request.POST.get("version", vendedor.version))
        if form.is_valid():
            try:
                estado_anterior = vendedor.estado
                nuevo_estado = form.cleaned_data["estado"]
                accion = (
                    AccionAuditoria.BLOQUEO if nuevo_estado == EstadoVendedor.BLOQUEADO
                    else AccionAuditoria.CAMBIO_ESTADO if nuevo_estado != estado_anterior
                    else AccionAuditoria.ACTUALIZACION
                )

                vendedor.optimistic_update(
                    expected_version=expected_version,
                    usuario=request.user,
                    accion=accion,
                    aliado=form.cleaned_data["aliado"],
                    coordinador=form.cleaned_data["coordinador"],
                    documento=form.cleaned_data["documento"],
                    nombre_completo=form.cleaned_data["nombre_completo"],
                    correo=form.cleaned_data["correo"],
                    telefono=form.cleaned_data["telefono"],
                    cargo=form.cleaned_data["cargo"],
                    ciudad_base=form.cleaned_data["ciudad_base"],
                    estado=nuevo_estado,
                    motivo_estado=form.cleaned_data["motivo_estado"],
                    fecha_ingreso=form.cleaned_data["fecha_ingreso"],
                )
                # Actualizar M2M ciudades_operacion
                vendedor.ciudades_operacion.set(form.cleaned_data["ciudades_operacion"])

                messages.success(request, f"Ficha de '{vendedor.nombre_completo}' actualizada.")
                return redirect(reverse("vendedor_list"))
            except ConcurrentModificationError as e:
                vendedor.refresh_from_db()
                form = VendedorForm(instance=vendedor)
                return render(
                    request,
                    "red_comercial/vendedor_form.html",
                    {"form": form, "titulo": f"Editar Ficha: {vendedor.nombre_completo}", "concurrency_error": str(e), "vendedor": vendedor},
                    status=409,
                )
    else:
        form = VendedorForm(instance=vendedor)
    return render(request, "red_comercial/vendedor_form.html", {"form": form, "titulo": f"Editar Ficha: {vendedor.nombre_completo}", "vendedor": vendedor})


# ==============================================================================
# HISTORIAL DE AUDITORÍA (AUDIT LOG VIEW)
# ==============================================================================

@requerir_roles("ADMIN", "ALIADO")
def audit_log_list_view(request: HttpRequest) -> HttpResponse:
    entidad_filtro = request.GET.get("entidad", "")
    logs_qs = AuditLog.objects.select_related("usuario").all().order_by("-fecha_evento")

    if entidad_filtro:
        logs_qs = logs_qs.filter(entidad=entidad_filtro)

    paginador = Paginator(logs_qs, 25)
    page_number = request.GET.get("page")
    page_obj = paginador.get_page(page_number)

    return render(
        request,
        "red_comercial/audit_list.html",
        {"page_obj": page_obj, "entidad_filtro": entidad_filtro},
    )
