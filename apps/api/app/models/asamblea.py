"""Asambleas de copropietarios (migración 0010, docs/ASAMBLEAS.md)."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import FetchedValue, Numeric
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TEXT
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPk
from app.models.enums import (
    ConvocatoriaAsamblea,
    EstadoAsamblea,
    EstadoPunto,
    MayoriaPunto,
    ModalidadAsamblea,
    TipoAsamblea,
    TipoAsistente,
    TipoPunto,
    pg_enum,
)

Coef = Numeric(7, 4)
_DB = {"server_default": FetchedValue()}
_DB_ALWAYS = {"server_default": FetchedValue(), "server_onupdate": FetchedValue()}
_EAGER = {"eager_defaults": True}


class Asamblea(UUIDPk, Base):
    __tablename__ = "asambleas"
    __mapper_args__ = _EAGER

    tenant_id: Mapped[uuid.UUID]
    consecutivo: Mapped[int] = mapped_column(**_DB)
    titulo: Mapped[str]
    tipo: Mapped[TipoAsamblea] = mapped_column(pg_enum(TipoAsamblea, "tipo_asamblea"), default=TipoAsamblea.ORDINARIA)
    modalidad: Mapped[ModalidadAsamblea] = mapped_column(
        pg_enum(ModalidadAsamblea, "modalidad_asamblea"), default=ModalidadAsamblea.PRESENCIAL
    )
    convocatoria: Mapped[ConvocatoriaAsamblea] = mapped_column(
        pg_enum(ConvocatoriaAsamblea, "convocatoria_asamblea"), default=ConvocatoriaAsamblea.PRIMERA
    )
    fecha_hora: Mapped[datetime]
    lugar: Mapped[str | None]
    estado: Mapped[EstadoAsamblea] = mapped_column(
        pg_enum(EstadoAsamblea, "estado_asamblea"), default=EstadoAsamblea.PROGRAMADA
    )
    max_poderes_por_apoderado: Mapped[int] = mapped_column(default=2)
    circular_id: Mapped[uuid.UUID | None]
    presidente: Mapped[str | None]
    secretario: Mapped[str | None]
    coeficiente_total: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    abierta_at: Mapped[datetime | None]
    cerrada_at: Mapped[datetime | None]
    acta_document_id: Mapped[uuid.UUID | None]
    observaciones: Mapped[str | None]
    creada_por_id: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime] = mapped_column(**_DB)
    updated_at: Mapped[datetime] = mapped_column(**_DB_ALWAYS)


class PadronAsamblea(Base):
    __tablename__ = "asamblea_padron"

    asamblea_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    unidad_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    etiqueta: Mapped[str]
    coeficiente: Mapped[Decimal] = mapped_column(Coef)
    propietarios: Mapped[str | None]
    votante_user_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(PGUUID(as_uuid=True)), default=list)
    al_dia: Mapped[bool | None]


class AsistenciaAsamblea(UUIDPk, Base):
    __tablename__ = "asamblea_asistencias"
    __mapper_args__ = _EAGER

    tenant_id: Mapped[uuid.UUID]
    asamblea_id: Mapped[uuid.UUID]
    unidad_id: Mapped[uuid.UUID]
    tipo: Mapped[TipoAsistente] = mapped_column(pg_enum(TipoAsistente, "tipo_asistente"))
    asistente_nombre: Mapped[str]
    asistente_documento: Mapped[str | None]
    user_id: Mapped[uuid.UUID | None]
    virtual: Mapped[bool] = mapped_column(default=False)
    poder_soporte_key: Mapped[str | None]
    registrada_por_id: Mapped[uuid.UUID | None]
    llegada_at: Mapped[datetime] = mapped_column(**_DB)
    retiro_at: Mapped[datetime | None]


class PuntoAsamblea(UUIDPk, Base):
    __tablename__ = "asamblea_puntos"
    __mapper_args__ = _EAGER

    tenant_id: Mapped[uuid.UUID]
    asamblea_id: Mapped[uuid.UUID]
    orden: Mapped[int]
    titulo: Mapped[str]
    descripcion: Mapped[str | None]
    tipo: Mapped[TipoPunto] = mapped_column(pg_enum(TipoPunto, "tipo_punto"), default=TipoPunto.INFORMATIVO)
    mayoria: Mapped[MayoriaPunto | None] = mapped_column(pg_enum(MayoriaPunto, "mayoria_punto"))
    opciones: Mapped[list[str]] = mapped_column(ARRAY(TEXT), default=list)
    estado: Mapped[EstadoPunto] = mapped_column(pg_enum(EstadoPunto, "estado_punto"), default=EstadoPunto.PENDIENTE)
    abierto_at: Mapped[datetime | None]
    cerrado_at: Mapped[datetime | None]
    coeficiente_presente: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    resultado: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    aprobado: Mapped[bool | None]
    conclusion: Mapped[str | None]


class VotoAsamblea(UUIDPk, Base):
    __tablename__ = "asamblea_votos"
    __mapper_args__ = _EAGER

    tenant_id: Mapped[uuid.UUID]
    asamblea_id: Mapped[uuid.UUID]
    punto_id: Mapped[uuid.UUID]
    unidad_id: Mapped[uuid.UUID]
    opcion: Mapped[str]
    coeficiente: Mapped[Decimal] = mapped_column(Coef, **_DB)  # lo fija el trigger desde el padrón
    emitido_por_id: Mapped[uuid.UUID | None]
    desde_portal: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(**_DB)
