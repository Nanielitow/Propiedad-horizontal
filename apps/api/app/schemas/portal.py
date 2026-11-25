"""Esquemas de entrada del portal del residente: PQRS, circulares y reservas."""

import uuid
from datetime import date, time
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import CanalPqrs, CategoriaCircular, CategoriaPqrs, EstadoPqrs, PrioridadPqrs, TipoPqrs

Texto = Annotated[str, Field(min_length=1, max_length=4000)]


class _Base(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class Adjunto(_Base):
    key: Annotated[str, Field(max_length=300)]
    nombre: Annotated[str, Field(min_length=1, max_length=200)]


Adjuntos = Annotated[list[Adjunto], Field(max_length=5)]


class AdjuntoUploadIn(_Base):
    content_type: str
    size_bytes: Annotated[int, Field(gt=0)]


# --- PQRS --------------------------------------------------------------------------------


class PqrsIn(_Base):
    tipo: TipoPqrs
    categoria: CategoriaPqrs
    asunto: Annotated[str, Field(min_length=5, max_length=200)]
    descripcion: Annotated[str, Field(min_length=10, max_length=4000)]
    unidad_id: uuid.UUID | None = None
    adjuntos: Adjuntos = []
    # Solo el personal, al radicar a nombre de alguien (presencial, correo, teléfono)
    canal: CanalPqrs = CanalPqrs.PORTAL
    solicitante_nombre: Annotated[str, Field(min_length=2, max_length=200)] | None = None
    solicitante_contacto: Annotated[str, Field(max_length=200)] | None = None
    prioridad: PrioridadPqrs | None = None


class MensajeIn(_Base):
    texto: Texto
    interno: bool = False  # nota del personal que el residente no ve
    adjuntos: Adjuntos = []


class RespuestaIn(_Base):
    """Respuesta formal de la administración: la PQRS queda RESPONDIDA y se avisa por correo."""

    texto: Annotated[str, Field(min_length=10, max_length=4000)]
    adjuntos: Adjuntos = []


class GestionPqrsIn(_Base):
    estado: EstadoPqrs | None = None
    asignado_a_id: uuid.UUID | None = None
    quitar_asignacion: bool = False
    prioridad: PrioridadPqrs | None = None
    categoria: CategoriaPqrs | None = None


class CalificacionIn(_Base):
    calificacion: Annotated[int, Field(ge=1, le=5)]
    comentario: Annotated[str, Field(max_length=1000)] | None = None


class ReabrirIn(_Base):
    texto: Annotated[str, Field(min_length=5, max_length=4000)]


class NovedadDesdePqrsIn(_Base):
    activo_id: uuid.UUID
    prioridad: Annotated[str, Field(pattern="^(BAJA|MEDIA|ALTA|CRITICA)$")] = "MEDIA"


# --- Circulares ----------------------------------------------------------------------------


class CircularIn(_Base):
    titulo: Annotated[str, Field(min_length=3, max_length=200)]
    cuerpo: Annotated[str, Field(min_length=10, max_length=20000)]
    categoria: CategoriaCircular = CategoriaCircular.INFORMATIVA
    importante: bool = False
    torres: Annotated[list[Annotated[str, Field(min_length=1, max_length=20)]], Field(max_length=50)] = []
    document_id: uuid.UUID | None = None
    enviar_correo: bool = True
    vigente_hasta: date | None = None


class CircularUpdate(_Base):
    titulo: Annotated[str, Field(min_length=3, max_length=200)] | None = None
    cuerpo: Annotated[str, Field(min_length=10, max_length=20000)] | None = None
    categoria: CategoriaCircular | None = None
    importante: bool | None = None
    torres: Annotated[list[Annotated[str, Field(min_length=1, max_length=20)]], Field(max_length=50)] | None = None
    document_id: uuid.UUID | None = None
    enviar_correo: bool | None = None
    vigente_hasta: date | None = None


# --- Zonas y reservas ----------------------------------------------------------------------


class ReglasZonaIn(_Base):
    descripcion: Annotated[str, Field(max_length=1000)] | None = None
    capacidad: Annotated[int, Field(gt=0, le=5000)] | None = None
    reglas: Annotated[str, Field(max_length=4000)] | None = None
    hora_apertura: time | None = None
    hora_cierre: time | None = None
    anticipacion_min_dias: Annotated[int, Field(ge=0, le=60)] | None = None
    anticipacion_max_dias: Annotated[int, Field(ge=1, le=365)] | None = None
    max_reservas_mes_unidad: Annotated[int, Field(ge=1, le=31)] | None = None
    requiere_paz_y_salvo: bool | None = None
    requiere_aprobacion: bool | None = None
    reservable_residentes: bool | None = None


class ReservaPortalIn(_Base):
    zona_id: uuid.UUID
    unidad_id: uuid.UUID
    fecha_evento: date
    hora_inicio: time
    hora_fin: time
    numero_asistentes: Annotated[int, Field(gt=0, le=5000)] | None = None
    observaciones: Annotated[str, Field(max_length=1000)] | None = None


class DecisionReservaIn(_Base):
    aprobar: bool
    motivo: Annotated[str, Field(max_length=1000)] | None = None

    @model_validator(mode="after")
    def _motivo(self) -> "DecisionReservaIn":
        if not self.aprobar and (not self.motivo or len(self.motivo) < 5):
            raise ValueError("Indique el motivo del rechazo (mínimo 5 caracteres)")
        return self


class CancelarReservaIn(_Base):
    motivo: Annotated[str, Field(min_length=3, max_length=1000)]
