"""Esquemas de salida del módulo de asambleas."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import (
    ConvocatoriaAsamblea,
    EstadoAsamblea,
    EstadoPunto,
    MayoriaPunto,
    ModalidadAsamblea,
    TipoAsamblea,
    TipoAsistente,
    TipoPunto,
)


class QuorumOut(BaseModel):
    presente: Decimal
    total: Decimal
    porcentaje: Decimal
    unidades_presentes: int
    unidades_total: int
    hay_quorum: bool
    falta: Decimal
    mensaje: str


class ResultadoOut(BaseModel):
    por_opcion: dict[str, Decimal]
    unidades_por_opcion: dict[str, int]
    votantes: Decimal
    presente: Decimal
    total: Decimal
    aprobado: bool | None
    ganador: str | None
    umbral: Decimal
    explicacion: str


class PuntoOut(BaseModel):
    id: uuid.UUID
    orden: int
    titulo: str
    descripcion: str | None
    tipo: TipoPunto
    mayoria: MayoriaPunto | None
    opciones: list[str]
    estado: EstadoPunto
    abierto_at: datetime | None
    cerrado_at: datetime | None
    resultado: ResultadoOut | None  # en vivo mientras se vota; fijo al cerrar
    aprobado: bool | None
    conclusion: str | None
    votos: int
    mis_votos: dict[str, str]  # etiqueta de la unidad -> opción (residente)


class PadronOut(BaseModel):
    unidad_id: uuid.UUID
    etiqueta: str
    coeficiente: Decimal
    propietarios: str | None
    al_dia: bool | None
    presente: bool
    asistencia_id: uuid.UUID | None
    asistente: str | None
    tipo: TipoAsistente | None
    virtual: bool
    llegada_at: datetime | None
    con_cuenta: bool


class AsambleaResumen(BaseModel):
    id: uuid.UUID
    consecutivo: int
    titulo: str
    tipo: TipoAsamblea
    modalidad: ModalidadAsamblea
    convocatoria: ConvocatoriaAsamblea
    fecha_hora: datetime
    lugar: str | None
    estado: EstadoAsamblea
    convocada: bool
    puntos: int
    quorum_pct: Decimal | None
    acta_document_id: uuid.UUID | None


class AsambleaDetalle(AsambleaResumen):
    max_poderes_por_apoderado: int
    presidente: str | None
    secretario: str | None
    observaciones: str | None
    abierta_at: datetime | None
    cerrada_at: datetime | None
    circular_id: uuid.UUID | None
    quorum: QuorumOut | None
    puntos_lista: list[PuntoOut]
    padron: list[PadronOut]  # personal: completo; residente: solo sus unidades
    soy_votante: bool  # el usuario figura como propietario con cuenta en el padrón
    puede_asistir_portal: bool
