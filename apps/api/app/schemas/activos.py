"""Esquemas de entrada del módulo de activos y mantenimiento."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models.enums import (
    BaseCalculo,
    Criticidad,
    EstadoActivo,
    EstadoNovedad,
    EstadoRecomendacion,
    Periodicidad,
    PrioridadNovedad,
    PrioridadRecomendacion,
    TipoDocumentoActivo,
    TipoMantenimiento,
)

Texto = Annotated[str, Field(min_length=1, max_length=200)]
TextoLargo = Annotated[str, Field(max_length=4000)]
Dinero = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
Motivo = Annotated[str, Field(min_length=10, max_length=1000)]


class _Base(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


def _especificaciones(v: dict[str, Any]) -> dict[str, Any]:
    if len(v) > 50:
        raise ValueError("Máximo 50 especificaciones")
    for k, val in v.items():
        if not isinstance(k, str) or not k.strip() or len(k) > 80:
            raise ValueError("Cada especificación necesita un nombre de hasta 80 caracteres")
        if not isinstance(val, str | int | float | bool) or len(str(val)) > 300:
            raise ValueError(f"El valor de «{k}» debe ser un texto o número corto")
    return v


# --- Contratistas -----------------------------------------------------------------


class ContratistaIn(_Base):
    razon_social: Annotated[str, Field(min_length=2, max_length=200)]
    nit: Annotated[str, Field(max_length=20)] | None = None
    contacto_nombre: Texto | None = None
    telefono: Annotated[str, Field(max_length=40)] | None = None
    email: EmailStr | None = None
    especialidades: Annotated[list[Texto], Field(max_length=20)] = []
    vigencia_contrato_inicio: date | None = None
    vigencia_contrato_fin: date | None = None
    alcance_contrato: TextoLargo | None = None
    periodicidad_pactada: Texto | None = None
    valor_contrato: Dinero | None = None
    contrato_documento_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _vigencia(self) -> "ContratistaIn":
        ini, fin = self.vigencia_contrato_inicio, self.vigencia_contrato_fin
        if ini and fin and fin < ini:
            raise ValueError("El fin del contrato es anterior a su inicio")
        return self


class ContratistaUpdate(ContratistaIn):
    razon_social: Annotated[str, Field(min_length=2, max_length=200)] | None = None  # type: ignore[assignment]
    activo: bool | None = None


# --- Activos ------------------------------------------------------------------------


class ActivoIn(_Base):
    nombre: Annotated[str, Field(min_length=2, max_length=200)]
    categoria_id: uuid.UUID
    subtipo: Texto | None = None
    ubicacion: Annotated[str, Field(min_length=2, max_length=200)]
    marca: Texto | None = None
    modelo: Texto | None = None
    fabricante: Texto | None = None
    numero_serie: Texto | None = None
    especificaciones: dict[str, Any] = {}
    vida_util_anios: Annotated[int, Field(ge=1, le=200)] | None = None
    fecha_instalacion: date | None = None
    instalador_id: uuid.UUID | None = None
    mantenedor_id: uuid.UUID | None = None
    fecha_vencimiento_garantia: date | None = None
    criticidad: Criticidad = Criticidad.MEDIA

    _esp = field_validator("especificaciones")(_especificaciones)


class ActivoUpdate(_Base):
    nombre: Annotated[str, Field(min_length=2, max_length=200)] | None = None
    categoria_id: uuid.UUID | None = None
    subtipo: Texto | None = None
    ubicacion: Annotated[str, Field(min_length=2, max_length=200)] | None = None
    marca: Texto | None = None
    modelo: Texto | None = None
    fabricante: Texto | None = None
    numero_serie: Texto | None = None
    especificaciones: dict[str, Any] | None = None
    vida_util_anios: Annotated[int, Field(ge=1, le=200)] | None = None
    fecha_instalacion: date | None = None
    instalador_id: uuid.UUID | None = None
    mantenedor_id: uuid.UUID | None = None
    fecha_vencimiento_garantia: date | None = None
    criticidad: Criticidad | None = None
    # Cambio manual de estado (p. ej. poner fuera de servicio sin intervención); no admite DADO_DE_BAJA
    estado: EstadoActivo | None = None
    motivo: Annotated[str, Field(min_length=5, max_length=1000)]

    @field_validator("especificaciones")
    @classmethod
    def _esp(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return None if v is None else _especificaciones(v)

    @field_validator("estado")
    @classmethod
    def _sin_baja(cls, v: EstadoActivo | None) -> EstadoActivo | None:
        if v == EstadoActivo.DADO_DE_BAJA:
            raise ValueError("Para dar de baja use la acción «Dar de baja»")
        return v


class BajaIn(_Base):
    motivo: Motivo
    fecha_baja: date | None = None


class VinculoDocumentoIn(_Base):
    document_id: uuid.UUID
    tipo: TipoDocumentoActivo
    fecha_documento: date | None = None


class LecturaIn(_Base):
    horas_acumuladas: Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=1)]


# --- Planes y actividades ------------------------------------------------------------


class PlanIn(_Base):
    activo_id: uuid.UUID
    nombre: Annotated[str, Field(min_length=3, max_length=200)]
    actividades_checklist: Annotated[list[Texto], Field(max_length=50)] = []
    periodicidad: Periodicidad
    intervalo_horas: Annotated[int, Field(gt=0, le=100000)] | None = None
    base_calculo: BaseCalculo = BaseCalculo.CALENDARIO_FIJO
    fecha_inicio: date
    contratista_id: uuid.UUID | None = None
    costo_estimado: Dinero | None = None

    @model_validator(mode="after")
    def _horas(self) -> "PlanIn":
        if (self.periodicidad == Periodicidad.POR_HORAS_USO) != (self.intervalo_horas is not None):
            raise ValueError("El intervalo en horas se indica solo (y siempre) en los planes por horas de uso")
        return self


class PlanUpdate(_Base):
    nombre: Annotated[str, Field(min_length=3, max_length=200)] | None = None
    actividades_checklist: Annotated[list[Texto], Field(max_length=50)] | None = None
    contratista_id: uuid.UUID | None = None
    costo_estimado: Dinero | None = None


class ReprogramacionIn(_Base):
    nueva_fecha: date
    motivo: Motivo


class AsignacionIn(_Base):
    asignado_a_id: uuid.UUID | None


# --- Mantenimientos y recomendaciones ------------------------------------------------


class RecomendacionNueva(_Base):
    descripcion: Annotated[str, Field(min_length=5, max_length=1000)]
    prioridad: PrioridadRecomendacion = PrioridadRecomendacion.MEDIA
    costo_estimado: Dinero | None = None
    fecha_limite: date | None = None
    responsable_id: uuid.UUID | None = None


class ItemChecklist(_Base):
    actividad: Texto
    resultado: Annotated[str, Field(pattern="^(HECHO|NO_APLICA|PENDIENTE)$")]
    nota: Annotated[str, Field(max_length=300)] | None = None


class MantenimientoIn(_Base):
    activo_id: uuid.UUID
    tipo: TipoMantenimiento
    fecha_ejecucion: date
    nombre_tecnico: Annotated[str, Field(min_length=2, max_length=200)]
    actividades_realizadas: Annotated[str, Field(min_length=5, max_length=4000)]
    estado_post_intervencion: EstadoActivo
    contratista_id: uuid.UUID | None = None
    tiempo_ejecucion_horas: Annotated[Decimal, Field(ge=0, le=9999, decimal_places=2)] | None = None
    diagnostico_inicial: TextoLargo | None = None
    repuestos_utilizados: TextoLargo | None = None
    novedades_encontradas: TextoLargo | None = None
    recomendaciones_tecnico: TextoLargo | None = None
    checklist: Annotated[list[ItemChecklist], Field(max_length=50)] = []
    costo_mano_obra: Dinero = Decimal(0)
    costo_repuestos: Dinero = Decimal(0)
    fecha_proximo_recomendado: date | None = None
    actividad_id: uuid.UUID | None = None
    novedad_id: uuid.UUID | None = None
    informe_documento_id: uuid.UUID | None = None
    factura_documento_id: uuid.UUID | None = None
    # Cada recomendación accionable del técnico se convierte en una tarea rastreable
    recomendaciones: Annotated[list[RecomendacionNueva], Field(max_length=20)] = []

    @field_validator("estado_post_intervencion")
    @classmethod
    def _sin_baja(cls, v: EstadoActivo) -> EstadoActivo:
        if v == EstadoActivo.DADO_DE_BAJA:
            raise ValueError("Un mantenimiento no da de baja un activo")
        return v


class AnulacionIn(_Base):
    motivo: Motivo


class RecomendacionIn(RecomendacionNueva):
    activo_id: uuid.UUID


class RecomendacionUpdate(_Base):
    estado: EstadoRecomendacion | None = None
    prioridad: PrioridadRecomendacion | None = None
    responsable_id: uuid.UUID | None = None
    fecha_limite: date | None = None
    costo_estimado: Dinero | None = None
    observaciones_administracion: TextoLargo | None = None
    justificacion_descarte: Annotated[str, Field(min_length=10, max_length=1000)] | None = None
    mantenimiento_ejecucion_id: uuid.UUID | None = None


# --- Novedades ---------------------------------------------------------------------------


class NovedadIn(_Base):
    activo_id: uuid.UUID
    descripcion: Annotated[str, Field(min_length=5, max_length=4000)]
    prioridad: PrioridadNovedad = PrioridadNovedad.MEDIA
    riesgo_identificado: TextoLargo | None = None
    # Con prioridad crítica, poner el activo fuera de servicio en el mismo paso
    poner_fuera_de_servicio: bool = False


class NovedadAvance(_Base):
    """Paso a otro estado del flujo, con los datos que correspondan a ese paso."""

    estado: EstadoNovedad
    contratista_asignado_id: uuid.UUID | None = None
    asignado_a_id: uuid.UUID | None = None
    cotizacion_id: uuid.UUID | None = None
    diagnostico: TextoLargo | None = None
    solucion_implementada: TextoLargo | None = None
    costo_reparacion: Dinero | None = None
    motivo_descarte: Annotated[str, Field(min_length=10, max_length=1000)] | None = None
    nota: Annotated[str, Field(max_length=1000)] | None = None
