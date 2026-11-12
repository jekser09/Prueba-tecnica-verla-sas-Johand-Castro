from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Sum
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from operacion.forms import MetaMensualForm, OfertaPeriodoForm
from operacion.models import MetaMensual, OfertaPeriodo
from red_comercial.models import (
    AccionAuditoria,
    Aliado,
    AuditLog,
    ConcurrentModificationError,
    Coordinador,
    EstadoVendedor,
    Vendedor,
)
from red_comercial.rbac import obtener_perfil_actor, requerir_roles


# ==============================================================================
# DASHBOARD DE METAS & RESULTADOS (AGREGACIÓN POR ROL Y NIVEL)
# ==============================================================================

@requerir_roles("ADMIN", "ALIADO", "COORDINADOR", "VENDEDOR")
def operacion_dashboard_view(request: HttpRequest) -> HttpResponse:
    """
    Dashboard de operaciones: si es Vendedor activo, muestra directamente sus metas personales
    y ofertas vigentes. Si es Administrador, Aliado o Coordinador, muestra métricas agregadas
    con drill-down y acceso a creación de ofertas/metas.
    """
    perfil = obtener_perfil_actor(request.user)
    # Soporte para filtro por año y mes independientes o parámetro 'periodo' unificado
    anio_param = request.GET.get("anio")
    mes_param = request.GET.get("mes")
    if anio_param and mes_param:
        periodo_actual = f"{anio_param.strip()}-{mes_param.strip().zfill(2)}"
    else:
        periodo_actual = request.GET.get("periodo") or timezone.now().strftime("%Y-%m")

    # Extraer año y mes actuales para los selectores
    try:
        partes_periodo = periodo_actual.split("-")
        sel_anio = partes_periodo[0]
        sel_mes = partes_periodo[1]
    except Exception:
        sel_anio = timezone.now().strftime("%Y")
        sel_mes = timezone.now().strftime("%m")

    meses_opciones = [
        ("01", "Enero"),
        ("02", "Febrero"),
        ("03", "Marzo"),
        ("04", "Abril"),
        ("05", "Mayo"),
        ("06", "Junio"),
        ("07", "Julio"),
        ("08", "Agosto"),
        ("09", "Septiembre"),
        ("10", "Octubre"),
        ("11", "Noviembre"),
        ("12", "Diciembre"),
    ]
    anios_opciones = ["2025", "2026", "2027"]

    # Si es vendedor, renderizar la vista especializada de vendedor
    if perfil["es_vendedor"]:
        return mis_metas_y_ofertas_vendedor_view(request, perfil["objeto"], periodo_actual)

    # Filtrar metas según el alcance del rol
    metas_qs = MetaMensual.objects.select_related("vendedor__coordinador__aliado", "vendedor__coordinador", "vendedor__ciudad_base").filter(periodo=periodo_actual)

    if perfil["es_aliado"]:
        metas_qs = metas_qs.filter(vendedor__coordinador__aliado=perfil["objeto"])
    elif perfil["es_coordinador"]:
        metas_qs = metas_qs.filter(vendedor__coordinador=perfil["objeto"])

    totales = metas_qs.aggregate(
        total_meta=Sum("meta_valor"),
        total_real=Sum("resultado_real"),
    )
    total_meta = totales["total_meta"] or Decimal("0.00")
    total_real = totales["total_real"] or Decimal("0.00")
    porcentaje_global = round((total_real / total_meta * 100), 1) if total_meta > 0 else Decimal("0.0")

    # Agregaciones estructuradas
    resumen_coordinadores = MetaMensual.resumen_por_coordinador(periodo_actual)
    if perfil["es_aliado"]:
        resumen_coordinadores = resumen_coordinadores.filter(vendedor__coordinador__aliado=perfil["objeto"])
    elif perfil["es_coordinador"]:
        resumen_coordinadores = resumen_coordinadores.filter(vendedor__coordinador=perfil["objeto"])

    resumen_aliados = MetaMensual.resumen_por_aliado(periodo_actual) if perfil["es_admin"] else None

    # Ofertas activas en el periodo
    ofertas_qs = OfertaPeriodo.objects.filter(periodo=periodo_actual, activa=True).order_by("-fecha_inicio")
    if perfil["es_aliado"]:
        ofertas_qs = ofertas_qs.filter(aliado__in=[None, perfil["objeto"]])
    elif perfil["es_coordinador"]:
        # El coordinador solo ve ofertas generales o las de su aliado
        ofertas_qs = ofertas_qs.filter(aliado__in=[None, perfil["objeto"].aliado])

    context = {
        "periodo_actual": periodo_actual,
        "sel_anio": sel_anio,
        "sel_mes": sel_mes,
        "meses_opciones": meses_opciones,
        "anios_opciones": anios_opciones,
        "total_meta": total_meta,
        "total_real": total_real,
        "porcentaje_global": porcentaje_global,
        "metas": metas_qs.order_by("vendedor__nombre_completo"),
        "resumen_coordinadores": resumen_coordinadores,
        "resumen_aliados": resumen_aliados,
        "ofertas": ofertas_qs,
    }
    return render(request, "operacion/dashboard.html", context)


def mis_metas_y_ofertas_vendedor_view(request: HttpRequest, vendedor: Vendedor, periodo: str) -> HttpResponse:
    """Vista personalizada para el vendedor autenticado con sus metas y ofertas aplicables."""
    metas_vendedor = MetaMensual.objects.filter(vendedor=vendedor).order_by("-periodo")
    meta_periodo = metas_vendedor.filter(periodo=periodo).first()

    # Ofertas vigentes para el alcance del vendedor (su aliado o generales, y sus ciudades de operación o base)
    ciudades_ids = list(vendedor.ciudades_operacion.values_list("id", flat=True))
    if vendedor.ciudad_base_id:
        ciudades_ids.append(vendedor.ciudad_base_id)

    hoy = timezone.localdate()
    ofertas_visibles = OfertaPeriodo.visibles_para_vendedor(vendedor, hoy).filter(activa=True)

    context = {
        "vendedor": vendedor,
        "periodo": periodo,
        "meta_periodo": meta_periodo,
        "historial_metas": metas_vendedor,
        "ofertas_visibles": ofertas_visibles,
    }
    return render(request, "operacion/vendedor_metas.html", context)


# ==============================================================================
# CRUD METAS MENSUALES (CONCURRENCIA OPTIMISTA 409)
# ==============================================================================

@requerir_roles("ADMIN", "COORDINADOR")
def meta_mensual_create_view(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = MetaMensualForm(request.POST, user=request.user)
        if form.is_valid():
            meta = form.save()
            messages.success(request, f"Meta registrada para {meta.vendedor.nombre_completo} ({meta.periodo}).")
            return redirect(reverse("op_default") + f"?periodo={meta.periodo}")
    else:
        initial_periodo = request.GET.get("periodo") or timezone.now().strftime("%Y-%m")
        form = MetaMensualForm(initial={"periodo": initial_periodo}, user=request.user)
    return render(request, "operacion/meta_form.html", {"form": form, "titulo": "Asignar Meta Mensual"})


@requerir_roles("ADMIN", "COORDINADOR")
def meta_mensual_update_view(request: HttpRequest, pk: int) -> HttpResponse:
    meta = get_object_or_404(MetaMensual, pk=pk)
    perfil = obtener_perfil_actor(request.user)

    # El coordinador solo puede editar metas de vendedores que él mismo supervisa
    if perfil["es_coordinador"] and meta.vendedor.coordinador_id != perfil["objeto"].pk:
        messages.error(request, "No tiene autorización para modificar metas de otra coordinación.")
        return redirect(reverse("op_default"))

    if request.method == "POST":
        form = MetaMensualForm(request.POST, instance=meta, user=request.user)
        expected_version = int(request.POST.get("version", meta.version))
        if form.is_valid():
            try:
                meta.optimistic_update(
                    expected_version=expected_version,
                    usuario=request.user,
                    accion=AccionAuditoria.ACTUALIZACION,
                    vendedor=form.cleaned_data["vendedor"],
                    periodo=form.cleaned_data["periodo"],
                    meta_valor=form.cleaned_data["meta_valor"],
                    resultado_real=form.cleaned_data["resultado_real"],
                    observaciones=form.cleaned_data["observaciones"],
                )
                messages.success(request, f"Meta actualizada para {meta.vendedor.nombre_completo}.")
                return redirect(reverse("op_default") + f"?periodo={meta.periodo}")
            except ConcurrentModificationError as e:
                meta.refresh_from_db()
                form = MetaMensualForm(instance=meta, user=request.user)
                return render(
                    request,
                    "operacion/meta_form.html",
                    {"form": form, "titulo": f"Editar Meta: {meta.vendedor.nombre_completo}", "concurrency_error": str(e), "meta": meta},
                    status=409,
                )
    else:
        form = MetaMensualForm(instance=meta, user=request.user)
    return render(request, "operacion/meta_form.html", {"form": form, "titulo": f"Editar Meta: {meta.vendedor.nombre_completo}", "meta": meta})


# ==============================================================================
# CRUD OFERTAS DEL PERIODO (IMÁGENES & CONCURRENCIA OPTIMISTA 409)
# ==============================================================================

@requerir_roles("ADMIN", "ALIADO")
def oferta_periodo_create_view(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = OfertaPeriodoForm(request.POST, request.FILES)
        if form.is_valid():
            oferta = form.save()
            messages.success(request, f"Oferta '{oferta.titulo}' creada con éxito.")
            return redirect(reverse("op_default") + f"?periodo={oferta.periodo}")
    else:
        initial_periodo = request.GET.get("periodo") or timezone.now().strftime("%Y-%m")
        hoy = timezone.now().date()
        form = OfertaPeriodoForm(initial={"periodo": initial_periodo, "fecha_inicio": hoy, "fecha_fin": hoy})
    return render(request, "operacion/oferta_form.html", {"form": form, "titulo": "Nueva Oferta Comercial"})


@requerir_roles("ADMIN", "ALIADO")
def oferta_periodo_update_view(request: HttpRequest, pk: int) -> HttpResponse:
    oferta = get_object_or_404(OfertaPeriodo, pk=pk)
    if request.method == "POST":
        form = OfertaPeriodoForm(request.POST, request.FILES, instance=oferta)
        expected_version = int(request.POST.get("version", oferta.version))
        if form.is_valid():
            try:
                # Si se sube una nueva imagen se actualiza en el campo
                campos_update = {
                    "titulo": form.cleaned_data["titulo"],
                    "descripcion": form.cleaned_data["descripcion"],
                    "periodo": form.cleaned_data["periodo"],
                    "fecha_inicio": form.cleaned_data["fecha_inicio"],
                    "fecha_fin": form.cleaned_data["fecha_fin"],
                    "activa": form.cleaned_data["activa"],
                    "aliado": form.cleaned_data["aliado"],
                }
                if form.cleaned_data.get("imagen"):
                    campos_update["imagen"] = form.cleaned_data["imagen"]

                oferta.optimistic_update(
                    expected_version=expected_version,
                    usuario=request.user,
                    accion=AccionAuditoria.ACTUALIZACION,
                    **campos_update,
                )
                oferta.ciudades.set(form.cleaned_data["ciudades"])

                messages.success(request, f"Oferta '{oferta.titulo}' actualizada exitosamente.")
                return redirect(reverse("op_default") + f"?periodo={oferta.periodo}")
            except ConcurrentModificationError as e:
                oferta.refresh_from_db()
                form = OfertaPeriodoForm(instance=oferta)
                return render(
                    request,
                    "operacion/oferta_form.html",
                    {"form": form, "titulo": f"Editar Oferta: {oferta.titulo}", "concurrency_error": str(e), "oferta": oferta},
                    status=409,
                )
    else:
        form = OfertaPeriodoForm(instance=oferta)
    return render(request, "operacion/oferta_form.html", {"form": form, "titulo": f"Editar Oferta: {oferta.titulo}", "oferta": oferta})


@require_POST
@requerir_roles("ADMIN", "ALIADO")
def oferta_periodo_cancel_delete_view(request: HttpRequest, pk: int) -> HttpResponseRedirect:
    oferta = get_object_or_404(OfertaPeriodo, pk=pk)
    perfil = obtener_perfil_actor(request.user)

    # Si es ALIADO, validar que la oferta pertenezca a su red (o sea global creada en su alcance)
    if perfil.get("es_aliado") and oferta.aliado_id:
        aliado_obj = perfil.get("objeto")
        if aliado_obj and oferta.aliado_id != aliado_obj.pk:
            messages.error(request, "No tiene permisos para cancelar o eliminar ofertas de otro aliado comercial.")
            return redirect(reverse("op_default") + f"?periodo={oferta.periodo}")

    periodo = oferta.periodo
    titulo = oferta.titulo

    # Se realiza soft delete (cancelación: activa=False) o hard delete si ya estaba inactiva
    action_type = request.POST.get("action_type", "cancelar")
    with transaction.atomic():
        if action_type == "eliminar":
            AuditLog.objects.create(
                entidad="OfertaPeriodo",
                registro_id=oferta.pk,
                accion=AccionAuditoria.ELIMINACION,
                usuario=request.user if getattr(request.user, "is_authenticated", False) else None,
                cambios_json={"titulo": oferta.titulo, "periodo": oferta.periodo, "activa": oferta.activa},
                version_resultante=oferta.version,
            )
            oferta.delete()
            messages.success(request, f"Oferta '{titulo}' eliminada permanentemente.")
        else:
            oferta.optimistic_update(
                expected_version=oferta.version,
                usuario=request.user,
                accion=AccionAuditoria.CAMBIO_ESTADO,
                activa=False,
            )
            messages.success(request, f"Oferta '{titulo}' cancelada y desactivada exitosamente.")

    return redirect(reverse("op_default") + f"?periodo={periodo}")
