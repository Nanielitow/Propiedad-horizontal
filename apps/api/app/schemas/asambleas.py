"""Esquemas de entrada del módulo de asambleas."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import (
    ConvocatoriaAsamblea,
    MayoriaPunto,
    ModalidadAsamblea,
    TipoAsamblea,
    TipoAsistente,
    TipoPunto,
)


class _Base(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


Opciones = Annotated[list[Annotated[str, Field(min_length=1, max_length=120)]], Field(max_length=30)]


class PuntoIn(_Base):
    titulo: Annotated[str, Field(min_length=3, max_length=300)]
    descripcion: Annotated[str, Field(max_length=4000)] | None = None
    tipo: TipoPunto = TipoPunto.INFORMATIVO
    mayoria: MayoriaPunto | None = None
    opciones: Opciones = []

    @model_validator(mode="after")
    def _votacion(self) -> "PuntoIn":
        if self.tipo == TipoPunto.VOTACION and self.mayoria is None:
            self.mayoria = MayoriaPunto.SIMPLE
        if self.tipo == TipoPunto.INFORMATIVO:
            self.mayoria = None
            self.opciones = []
        if self.mayoria == MayoriaPunto.ELECCION and len(self.opciones) < 2:
            raise ValueError("Para una elección indique al menos dos opciones (candidatos o planchas)")
        return self


class PuntoUpdate(_Base):
    titulo: Annotated[str, Field(min_length=3, max_length=300)] | None = None
    descripcion: Annotated[str, Field(max_length=4000)] | None = None
    conclusion: Annotated[str, Field(max_length=4000)] | None = None


class AsambleaIn(_Base):
    titulo: Annotated[str, Field(min_length=5, max_length=200)]
    tipo: TipoAsamblea = TipoAsamblea.ORDINARIA
    modalidad: ModalidadAsamblea = ModalidadAsamblea.PRESENCIAL
    convocatoria: ConvocatoriaAsamblea = ConvocatoriaAsamblea.PRIMERA
    fecha_hora: datetime
    lugar: Annotated[str, Field(max_length=300)] | None = None
    max_poderes_por_apoderado: Annotated[int, Field(ge=1, le=50)] = 2
    observaciones: Annotated[str, Field(max_length=4000)] | None = None
    puntos: Annotated[list[PuntoIn], Field(max_length=40)] = []


class AsambleaUpdate(_Base):
    titulo: Annotated[str, Field(min_length=5, max_length=200)] | None = None
    tipo: TipoAsamblea | None = None
    modalidad: ModalidadAsamblea | None = None
    convocatoria: ConvocatoriaAsamblea | None = None
    fecha_hora: datetime | None = None
    lugar: Annotated[str, Field(max_length=300)] | None = None
    max_poderes_por_apoderado: Annotated[int, Field(ge=1, le=50)] | None = None
    observaciones: Annotated[str, Field(max_length=4000)] | None = None


class AbrirIn(_Base):
    presidente: Annotated[str, Field(min_length=3, max_length=200)]
    secretario: Annotated[str, Field(min_length=3, max_length=200)]


class ConvocarIn(_Base):
    enviar_correo: bool = True
    mensaje: Annotated[str, Field(max_length=4000)] | None = None  # texto adicional en la circular


class AsistenciaIn(_Base):
    unidad_id: uuid.UUID
    tipo: TipoAsistente = TipoAsistente.PROPIETARIO
    asistente_nombre: Annotated[str, Field(min_length=3, max_length=200)]
    asistente_documento: Annotated[str, Field(min_length=3, max_length=30)] | None = None
    poder_soporte_key: Annotated[str, Field(max_length=300)] | None = None

    @model_validator(mode="after")
    def _poder(self) -> "AsistenciaIn":
        if self.tipo == TipoAsistente.APODERADO and not self.asistente_documento:
            raise ValueError("Del apoderado se registra el número de documento")
        return self


class VotoSalaIn(_Base):
    unidad_id: uuid.UUID
    opcion: Annotated[str, Field(min_length=1, max_length=120)]


class VotoPortalIn(_Base):
    opcion: Annotated[str, Field(min_length=1, max_length=120)]
    unidad_id: uuid.UUID | None = None  # None: todas las unidades del votante que estén presentes


class CerrarIn(_Base):
    observaciones: Annotated[str, Field(max_length=4000)] | None = None


class CancelarIn(_Base):
    motivo: Annotated[str, Field(min_length=10, max_length=1000)]
