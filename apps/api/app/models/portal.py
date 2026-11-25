"""Portal del residente: PQRS y circulares (migración 0009, docs/PORTAL.md).

Las reservas y las zonas sociales viven en app/models/recaudo.py (0003, ampliadas en 0009).
"""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import FetchedValue
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPk
from app.models.enums import (
    AccionAuditoria,
    CanalPqrs,
    CategoriaCircular,
    CategoriaPqrs,
    EstadoCircular,
    EstadoPqrs,
    PrioridadPqrs,
    TipoPqrs,
    pg_enum,
)

_DB = {"server_default": FetchedValue()}
_DB_ALWAYS = {"server_default": FetchedValue(), "server_onupdate": FetchedValue()}
_EAGER = {"eager_defaults": True}


class Pqrs(UUIDPk, Base):
    __tablename__ = "pqrs"
    __mapper_args__ = _EAGER

    tenant_id: Mapped[uuid.UUID]
    consecutivo: Mapped[int] = mapped_column(**_DB)  # trigger: radicado sin huecos
    tipo: Mapped[TipoPqrs] = mapped_column(pg_enum(TipoPqrs, "tipo_pqrs"))
    categoria: Mapped[CategoriaPqrs] = mapped_column(pg_enum(CategoriaPqrs, "categoria_pqrs"))
    asunto: Mapped[str]
    descripcion: Mapped[str]
    unidad_id: Mapped[uuid.UUID | None]
    canal: Mapped[CanalPqrs] = mapped_column(pg_enum(CanalPqrs, "canal_pqrs"), default=CanalPqrs.PORTAL)
    estado: Mapped[EstadoPqrs] = mapped_column(pg_enum(EstadoPqrs, "estado_pqrs"), default=EstadoPqrs.RADICADA)
    prioridad: Mapped[PrioridadPqrs] = mapped_column(
        pg_enum(PrioridadPqrs, "prioridad_pqrs"), default=PrioridadPqrs.MEDIA
    )
    radicado_por_id: Mapped[uuid.UUID]
    solicitante_nombre: Mapped[str]
    solicitante_contacto: Mapped[str | None]
    asignado_a_id: Mapped[uuid.UUID | None]
    fecha_limite: Mapped[date]
    respondida_at: Mapped[datetime | None] = mapped_column(**_DB_ALWAYS)
    cerrada_at: Mapped[datetime | None] = mapped_column(**_DB_ALWAYS)
    calificacion: Mapped[int | None]
    comentario_calificacion: Mapped[str | None]
    adjuntos: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    novedad_id: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime] = mapped_column(**_DB)
    updated_at: Mapped[datetime] = mapped_column(**_DB_ALWAYS)

    @property
    def radicado(self) -> str:
        return f"PQRS-{self.created_at.year if self.created_at else ''}-{self.consecutivo:04d}"


class PqrsMensaje(UUIDPk, Base):
    __tablename__ = "pqrs_mensajes"
    __mapper_args__ = _EAGER

    tenant_id: Mapped[uuid.UUID]
    pqrs_id: Mapped[uuid.UUID]
    autor_id: Mapped[uuid.UUID]
    autor_rol: Mapped[str]
    texto: Mapped[str]
    interno: Mapped[bool] = mapped_column(default=False)
    es_respuesta: Mapped[bool] = mapped_column(default=False)
    adjuntos: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(**_DB)


class Circular(UUIDPk, Base):
    __tablename__ = "circulares"
    __mapper_args__ = _EAGER

    tenant_id: Mapped[uuid.UUID]
    consecutivo: Mapped[int | None] = mapped_column(**_DB_ALWAYS)  # trigger: al publicar
    titulo: Mapped[str]
    cuerpo: Mapped[str]
    categoria: Mapped[CategoriaCircular] = mapped_column(
        pg_enum(CategoriaCircular, "categoria_circular"), default=CategoriaCircular.INFORMATIVA
    )
    importante: Mapped[bool] = mapped_column(default=False)
    torres: Mapped[list[str]] = mapped_column(ARRAY(TEXT), default=list)
    document_id: Mapped[uuid.UUID | None]
    estado: Mapped[EstadoCircular] = mapped_column(
        pg_enum(EstadoCircular, "estado_circular"), default=EstadoCircular.BORRADOR
    )
    enviar_correo: Mapped[bool] = mapped_column(default=True)
    publicada_at: Mapped[datetime | None] = mapped_column(**_DB_ALWAYS)
    publicada_por_id: Mapped[uuid.UUID | None]
    vigente_hasta: Mapped[date | None]
    correos_enviados: Mapped[int] = mapped_column(default=0)
    creada_por_id: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime] = mapped_column(**_DB)
    updated_at: Mapped[datetime] = mapped_column(**_DB_ALWAYS)


class CircularLectura(Base):
    __tablename__ = "circular_lecturas"

    circular_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    leida_at: Mapped[datetime] = mapped_column(**_DB)


class AuditoriaPortal(Base):
    """Solo lectura para la aplicación: la escribe un trigger de la base de datos."""

    __tablename__ = "auditoria_portal"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    entidad: Mapped[str]
    entidad_id: Mapped[uuid.UUID]
    usuario_id: Mapped[uuid.UUID | None]
    accion: Mapped[AccionAuditoria] = mapped_column(pg_enum(AccionAuditoria, "accion_auditoria"))
    valores_anteriores: Mapped[dict[str, Any] | None]
    valores_nuevos: Mapped[dict[str, Any] | None]
    fecha_hora: Mapped[datetime]
