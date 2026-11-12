from __future__ import annotations

import os
import time
from datetime import date
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q, QuerySet, Sum
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone
from django.utils.text import slugify

from red_comercial.models import VersionedModel

validador_periodo_mensual = RegexValidator(
    regex=r"^\d{4}-(0[1-9]|1[0-2])$",
    message="El periodo debe tener el formato YYYY-MM (por ejemplo, 2026-03).",
)


class MetaMensual(VersionedModel):
    """
    Meta mensual de ventas vs. resultado real alcanzado por un vendedor en un periodo YYYY-MM.
    Soporta agregación jerárquica por vendedor, coordinador y aliado comercial.
    """

    vendedor = models.ForeignKey(
        "red_comercial.Vendedor",
        verbose_name="Vendedor",
        on_delete=models.CASCADE,
        related_name="metas_mensuales",
    )
    periodo = models.CharField(
        "Periodo (YYYY-MM)",
        max_length=7,
        validators=[validador_periodo_mensual],
        db_index=True,
    )
    meta_valor = models.DecimalField("Meta mensual ($)", max_digits=14, decimal_places=2)
    resultado_real = models.DecimalField(
        "Resultado real ($)",
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    observaciones = models.CharField(
        "Observaciones",
        max_length=255,
        blank=True,
        default="",
    )

    class Meta:
        verbose_name = "Meta mensual"
        verbose_name_plural = "Metas mensuales"
        ordering = ["-periodo", "vendedor__nombre_completo"]
        constraints = [
            models.UniqueConstraint(
                fields=["vendedor", "periodo"],
                name="uniq_meta_vendedor_periodo",
            )
        ]

    def __str__(self) -> str:
        return f"{self.vendedor.nombre_completo} - {self.periodo}"

    @property
    def brecha(self) -> Decimal:
        """Diferencia entre el resultado real y la meta asignada (negativo indica déficit)."""
        return self.resultado_real - self.meta_valor

    @property
    def porcentaje_cumplimiento(self) -> Decimal:
        """Porcentaje de cumplimiento de la meta redondeado a dos decimales."""
        if self.meta_valor <= Decimal("0.00"):
            return Decimal("0.00")
        porcentaje = (self.resultado_real / self.meta_valor) * Decimal("100")
        return porcentaje.quantize(Decimal("0.01"))

    @classmethod
    def resumen_por_coordinador(cls, periodo: str, aliado_id: int | None = None) -> QuerySet:
        """Agrega metas y resultados reales por coordinador para un periodo dado."""
        qs = cls.objects.filter(periodo=periodo)
        if aliado_id is not None:
            qs = qs.filter(vendedor__coordinador__aliado_id=aliado_id)
        return (
            qs.values(
                "vendedor__coordinador_id",
                "vendedor__coordinador__nombre_completo",
                "vendedor__coordinador__aliado__razon_social",
            )
            .annotate(
                total_meta=Sum("meta_valor"),
                total_resultado=Sum("resultado_real"),
            )
            .order_by("vendedor__coordinador__nombre_completo")
        )

    @classmethod
    def resumen_por_aliado(cls, periodo: str) -> QuerySet:
        """Agrega metas y resultados reales por aliado comercial para un periodo dado."""
        return (
            cls.objects.filter(periodo=periodo)
            .values(
                "vendedor__coordinador__aliado_id",
                "vendedor__coordinador__aliado__razon_social",
            )
            .annotate(
                total_meta=Sum("meta_valor"),
                total_resultado=Sum("resultado_real"),
            )
            .order_by("vendedor__coordinador__aliado__razon_social")
        )


def ruta_imagen_oferta(instance: Any, filename: str) -> str:
    """
    Genera una ruta trazable e identificable para la pieza gráfica de la oferta,
    vinculando la entidad OfertaPeriodo, el periodo comercial y marca temporal
    para trazabilidad de auditoría y evitar colisiones en mediafiles.
    Formato: ofertas/<año>/<mes>/audit_oferta_<id_o_nueva>_<periodo>_<timestamp>_<slug>.<ext>
    """
    base, ext = os.path.splitext(filename)
    slug_nombre = slugify(base)[:30] or "grafica"
    ts = int(time.time())
    pk_str = str(instance.pk) if getattr(instance, "pk", None) else "nueva"
    periodo_limpio = (getattr(instance, "periodo", "") or "general").replace("-", "")

    periodo = getattr(instance, "periodo", "")
    if periodo and len(periodo) == 7 and "-" in periodo:
        año, mes = periodo.split("-")
    else:
        hoy = timezone.now()
        año, mes = hoy.strftime("%Y"), hoy.strftime("%m")

    nombre_archivo = f"audit_oferta_{pk_str}_{periodo_limpio}_{ts}_{slug_nombre}{ext.lower()}"
    return f"ofertas/{año}/{mes}/{nombre_archivo}"


def _eliminar_archivo_storage_seguro(storage: Any, path: str | None) -> None:
    """Elimina de forma segura un archivo del storage sin lanzar excepciones por bloqueo de Windows."""
    if not path:
        return
    try:
        if storage.exists(path):
            storage.delete(path)
    except Exception:
        import gc, time
        gc.collect()
        time.sleep(0.05)
        try:
            if storage.exists(path):
                storage.delete(path)
        except Exception:
            pass



class OfertaPeriodo(VersionedModel):
    """
    Oferta comercial vigente por periodo con texto dinámico, imagen promocional opcional
    y segmentación por aliado y ciudades de operación.
    """

    titulo = models.CharField("Título de la oferta", max_length=160)
    descripcion = models.TextField("Descripción y condiciones comerciales")
    imagen = models.ImageField(
        "Pieza gráfica promocional",
        upload_to=ruta_imagen_oferta,
        null=True,
        blank=True,
    )
    periodo = models.CharField(
        "Periodo (YYYY-MM)",
        max_length=7,
        validators=[validador_periodo_mensual],
        db_index=True,
    )
    fecha_inicio = models.DateField("Fecha de inicio de vigencia")
    fecha_fin = models.DateField("Fecha de fin de vigencia")
    activa = models.BooleanField("Oferta activa", default=True, db_index=True)
    aliado = models.ForeignKey(
        "red_comercial.Aliado",
        verbose_name="Aliado específico (opcional)",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="ofertas",
    )
    ciudades = models.ManyToManyField(
        "red_comercial.Ciudad",
        verbose_name="Ciudades objetivo",
        related_name="ofertas",
        blank=True,
    )

    class Meta:
        verbose_name = "Oferta del periodo"
        verbose_name_plural = "Ofertas del periodo"
        ordering = ["-fecha_inicio", "-id"]

    def __str__(self) -> str:
        return f"{self.titulo} ({self.periodo})"

    def clean(self) -> None:
        super().clean()
        if self.fecha_inicio and self.fecha_fin and self.fecha_fin < self.fecha_inicio:
            raise ValidationError(
                {
                    "fecha_fin": (
                        "La fecha de fin de vigencia no puede ser anterior a la fecha de inicio."
                    )
                }
            )

    @classmethod
    def visibles_para_vendedor(cls, vendedor, fecha: date | None = None) -> QuerySet[OfertaPeriodo]:
        """
        Retorna las ofertas vigentes visibles para un vendedor activo según su aliado
        y sus ciudades de operación (incluyendo su ciudad base).
        Si el vendedor está INACTIVO o BLOQUEADO (`not vendedor.puede_operar`), retorna vacío.
        """
        if not vendedor.puede_operar:
            return cls.objects.none()

        fecha_consulta = fecha or timezone.localdate()
        ciudades_ids = set(vendedor.ciudades_operacion.values_list("id", flat=True))
        if vendedor.ciudad_base_id:
            ciudades_ids.add(vendedor.ciudad_base_id)

        aliado_obj = vendedor.aliado
        aliado_id = aliado_obj.id if aliado_obj else None

        return (
            cls.objects.filter(
                activa=True,
                fecha_inicio__lte=fecha_consulta,
                fecha_fin__gte=fecha_consulta,
            )
            .filter(Q(aliado__isnull=True) | Q(aliado_id=aliado_id))
            .filter(Q(ciudades__isnull=True) | Q(ciudades__in=ciudades_ids) | Q(ciudades=None))
            .distinct()
        )

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        img_name = str(self.imagen.name) if self.imagen and self.imagen.name else None
        img_storage = self.imagen.storage if self.imagen else None
        if self.imagen and hasattr(self.imagen, "close"):
            try:
                self.imagen.close()
            except Exception:
                pass
        res = super().delete(*args, **kwargs)
        if img_name and img_storage:
            _eliminar_archivo_storage_seguro(img_storage, img_name)
        return res


@receiver(post_delete, sender=OfertaPeriodo)
def eliminar_imagen_oferta_en_delete(sender, instance, **kwargs):
    """
    Elimina físicamente el archivo gráfico de mediafiles al eliminarse
    la oferta comercial de la base de datos para no dejar huérfanos.
    """
    if instance.imagen and instance.imagen.name:
        if hasattr(instance.imagen, "close"):
            try:
                instance.imagen.close()
            except Exception:
                pass
        _eliminar_archivo_storage_seguro(instance.imagen.storage, instance.imagen.name)


