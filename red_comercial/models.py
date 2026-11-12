from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F
from django.utils import timezone


class ConcurrentModificationError(Exception):
    """
    Excepción lanzada cuando una actualización con bloqueo optimista (version)
    falla porque el registro fue modificado concurrentemente por otro actor.
    """


class AccionAuditoria(models.TextChoices):
    CREACION = "CREACION", "Creación"
    ACTUALIZACION = "ACTUALIZACION", "Actualización"
    CAMBIO_ESTADO = "CAMBIO_ESTADO", "Cambio de estado"
    BLOQUEO = "BLOQUEO", "Bloqueo operativo"
    ELIMINACION = "ELIMINACION", "Eliminación"


def _serializar_valor_auditoria(valor: Any) -> Any:
    """Convierte valores de campos del modelo a tipos primitivos serializables en JSON."""
    if valor is None or isinstance(valor, (str, int, float, bool)):
        return valor
    if isinstance(valor, models.Model):
        return valor.pk
    return str(valor)


class AuditLog(models.Model):
    """
    Bitácora inmutable de cambios e historial de auditoría para entidades del portal.
    """

    entidad = models.CharField("Entidad", max_length=80, db_index=True)
    registro_id = models.PositiveBigIntegerField("ID de registro", db_index=True)
    accion = models.CharField(
        "Acción",
        max_length=30,
        choices=AccionAuditoria.choices,
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Usuario actor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registros_auditoria",
    )
    cambios_json = models.JSONField("Diferencial de cambios (JSON)", default=dict)
    version_resultante = models.PositiveIntegerField("Versión resultante", default=1)
    fecha_evento = models.DateTimeField("Fecha del evento", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Registro de auditoría"
        verbose_name_plural = "Registros de auditoría"
        ordering = ["-fecha_evento", "-id"]

    def __str__(self) -> str:
        return f"{self.entidad}#{self.registro_id} [{self.accion}] v{self.version_resultante}"


class VersionedModel(models.Model):
    """
    Modelo base abstracto con control de concurrencia optimista (campo version)
    y trazabilidad automática hacia AuditLog.
    """

    version = models.PositiveIntegerField("Versión", default=1)
    creado_en = models.DateTimeField("Creado en", auto_now_add=True)
    actualizado_en = models.DateTimeField("Actualizado en", auto_now=True)

    class Meta:
        abstract = True

    def registrar_creacion(self, usuario: Any = None, detalle: dict[str, Any] | None = None) -> AuditLog:
        """Registra en AuditLog el evento inicial de creación de la entidad."""
        return AuditLog.objects.create(
            entidad=self.__class__.__name__,
            registro_id=self.pk,
            accion=AccionAuditoria.CREACION,
            usuario=usuario if getattr(usuario, "is_authenticated", False) else None,
            cambios_json=detalle or {},
            version_resultante=self.version,
        )

    def optimistic_update(
        self,
        *,
        expected_version: int,
        usuario: Any = None,
        accion: str | None = None,
        **fields: Any,
    ) -> VersionedModel:
        """
        Actualiza atómicamente los campos indicados validando que `version == expected_version`.
        Incrementa `version` en +1 y registra el diferencial antes/después en `AuditLog`.
        Lanza `ConcurrentModificationError` si la versión en base de datos ya cambió.
        """
        with transaction.atomic():
            valores_previos = {
                campo: _serializar_valor_auditoria(getattr(self, campo))
                for campo in fields
            }
            filas_afectadas = (
                type(self)
                .objects.filter(pk=self.pk, version=expected_version)
                .update(
                    version=F("version") + 1,
                    actualizado_en=timezone.now(),
                    **fields,
                )
            )
            if filas_afectadas == 0:
                raise ConcurrentModificationError(
                    "El registro fue modificado por otro usuario. Recargue antes de guardar."
                )

            self.refresh_from_db()
            cambios = {
                campo: {
                    "antes": valores_previos[campo],
                    "despues": _serializar_valor_auditoria(getattr(self, campo)),
                }
                for campo in fields
            }
            AuditLog.objects.create(
                entidad=self.__class__.__name__,
                registro_id=self.pk,
                accion=accion or AccionAuditoria.ACTUALIZACION,
                usuario=usuario if getattr(usuario, "is_authenticated", False) else None,
                cambios_json=cambios,
                version_resultante=self.version,
            )
            return self


class Ciudad(VersionedModel):
    """
    Catálogo de ciudades donde opera la red comercial de VERLA SAS.
    """

    codigo = models.CharField("Código", max_length=10, unique=True)
    nombre = models.CharField("Nombre de ciudad", max_length=120, unique=True)
    departamento = models.CharField("Departamento", max_length=120)
    activa = models.BooleanField("Activa", default=True)

    class Meta:
        verbose_name = "Ciudad"
        verbose_name_plural = "Ciudades"
        ordering = ["nombre"]

    def __str__(self) -> str:
        return f"{self.nombre} ({self.codigo})"


class Aliado(VersionedModel):
    """
    Aliado comercial titular de contrato y responsable de una red de coordinadores y vendedores.
    """

    nit = models.CharField("NIT", max_length=30, unique=True)
    razon_social = models.CharField("Razón social", max_length=180)
    codigo_contrato = models.CharField("Código de contrato", max_length=50, unique=True)
    correo_contacto = models.EmailField("Correo de contacto")
    telefono = models.CharField("Teléfono", max_length=30)
    activo = models.BooleanField("Activo", default=True)
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name="Usuario de portal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="perfil_aliado",
    )

    class Meta:
        verbose_name = "Aliado comercial"
        verbose_name_plural = "Aliados comerciales"
        ordering = ["razon_social"]

    def __str__(self) -> str:
        return f"{self.razon_social} ({self.nit})"


class Coordinador(VersionedModel):
    """
    Coordinador comercial adscrito a un Aliado y responsable de supervisar vendedores.
    """

    aliado = models.ForeignKey(
        Aliado,
        verbose_name="Aliado comercial",
        on_delete=models.PROTECT,
        related_name="coordinadores",
    )
    documento = models.CharField("Documento de identidad", max_length=30, unique=True)
    nombre_completo = models.CharField("Nombre completo", max_length=160)
    correo = models.EmailField("Correo electrónico")
    telefono = models.CharField("Teléfono", max_length=30)
    activo = models.BooleanField("Activo", default=True)
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name="Usuario de portal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="perfil_coordinador",
    )

    class Meta:
        verbose_name = "Coordinador"
        verbose_name_plural = "Coordinadores"
        ordering = ["nombre_completo"]

    def __str__(self) -> str:
        return f"{self.nombre_completo} - {self.aliado.razon_social}"


class EstadoVendedor(models.TextChoices):
    ACTIVO = "ACTIVO", "Activo"
    INACTIVO = "INACTIVO", "Inactivo"
    BLOQUEADO = "BLOQUEADO", "Bloqueado"


class Vendedor(VersionedModel):
    """
    Ficha de funcionario comercial (vendedor) con asignación a un Coordinador,
    ciudad base, operación multiciudad y control explícito de estados y bloqueos.
    El Aliado comercial se deriva de forma normalizada a través de su Coordinador responsable.
    """

    coordinador = models.ForeignKey(
        Coordinador,
        verbose_name="Coordinador responsable",
        on_delete=models.PROTECT,
        related_name="vendedores",
    )
    documento = models.CharField("Documento de identidad", max_length=30, unique=True)
    nombre_completo = models.CharField("Nombre completo", max_length=160)
    correo = models.EmailField("Correo electrónico")
    telefono = models.CharField("Teléfono", max_length=30)
    cargo = models.CharField("Cargo", max_length=100, default="Asesor Comercial")
    ciudad_base = models.ForeignKey(
        Ciudad,
        verbose_name="Ciudad base",
        on_delete=models.PROTECT,
        related_name="vendedores_base",
    )
    ciudades_operacion = models.ManyToManyField(
        Ciudad,
        verbose_name="Ciudades de operación",
        related_name="vendedores_operando",
        blank=True,
    )
    estado = models.CharField(
        "Estado operativo",
        max_length=15,
        choices=EstadoVendedor.choices,
        default=EstadoVendedor.ACTIVO,
        db_index=True,
    )
    motivo_estado = models.CharField(
        "Motivo de estado / bloqueo",
        max_length=255,
        blank=True,
        default="",
    )
    fecha_ingreso = models.DateField("Fecha de ingreso")
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name="Usuario de portal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="perfil_vendedor",
    )

    class Meta:
        verbose_name = "Vendedor"
        verbose_name_plural = "Vendedores"
        ordering = ["nombre_completo"]

    def __str__(self) -> str:
        return f"{self.nombre_completo} ({self.documento}) [{self.estado}]"

    def clean(self) -> None:
        super().clean()

    @property
    def aliado(self) -> Aliado | None:
        """Retorna el Aliado comercial titular a través de la asignación del Coordinador."""
        return self.coordinador.aliado if self.coordinador_id else None

    @property
    def puede_operar(self) -> bool:
        """Indica si el vendedor está habilitado para realizar operaciones y consultar ofertas activas."""
        return (
            self.estado == EstadoVendedor.ACTIVO
            and self.coordinador.activo
            and self.coordinador.aliado.activo
        )

    def cambiar_estado(
        self,
        *,
        nuevo_estado: str,
        expected_version: int,
        usuario: Any = None,
        motivo: str = "",
    ) -> Vendedor:
        """
        Cambia el estado operativo del vendedor aplicando control de concurrencia optimista
        y registrando el evento de bloqueo o cambio de estado en AuditLog.
        """
        accion = (
            AccionAuditoria.BLOQUEO
            if nuevo_estado == EstadoVendedor.BLOQUEADO
            else AccionAuditoria.CAMBIO_ESTADO
        )
        self.optimistic_update(
            expected_version=expected_version,
            usuario=usuario,
            accion=accion,
            estado=nuevo_estado,
            motivo_estado=motivo,
        )
        return self
