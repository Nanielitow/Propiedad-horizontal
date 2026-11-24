"""Unidades, directorio de personas, vínculos y vehículos (migración 0007, docs/UNIDADES.md).

La tabla `units` existe desde 0001 (torre, número, coeficiente); 0007 la amplía.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import FetchedValue, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPk
from app.models.enums import (
    AccionAuditoria,
    OcupacionUnidad,
    RelacionUnidad,
    TipoDocumentoIdentidad,
    TipoUnidad,
    TipoVehiculo,
    pg_enum,
)

_DB = {"server_default": FetchedValue()}
_DB_ALWAYS = {"server_default": FetchedValue(), "server_onupdate": FetchedValue()}
_EAGER = {"eager_defaults": True}


class Unit(UUIDPk, Base):
    __tablename__ = "units"
    __mapper_args__ = _EAGER

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    tower: Mapped[str] = mapped_column(default="")
    number: Mapped[str]
    coefficient: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    tipo: Mapped[TipoUnidad] = mapped_column(pg_enum(TipoUnidad, "tipo_unidad"), default=TipoUnidad.APARTAMENTO)
    unidad_principal_id: Mapped[uuid.UUID | None]
    area_m2: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    matricula_inmobiliaria: Mapped[str | None]
    ocupacion: Mapped[OcupacionUnidad] = mapped_column(
        pg_enum(OcupacionUnidad, "ocupacion_unidad"), default=OcupacionUnidad.SIN_INFORMACION
    )
    observaciones: Mapped[str | None]
    activa: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(**_DB)
    updated_at: Mapped[datetime] = mapped_column(**_DB_ALWAYS)

    @property
    def etiqueta(self) -> str:
        """'T2-301' o '301' si el conjunto no tiene torres."""
        return f"{self.tower}-{self.number}" if self.tower else self.number


class Persona(UUIDPk, Base):
    __tablename__ = "personas"
    __mapper_args__ = _EAGER

    tenant_id: Mapped[uuid.UUID]
    tipo_documento: Mapped[TipoDocumentoIdentidad | None] = mapped_column(
        pg_enum(TipoDocumentoIdentidad, "tipo_documento_identidad")
    )
    numero_documento: Mapped[str | None]
    nombre_completo: Mapped[str]
    email: Mapped[str | None]
    telefono: Mapped[str | None]
    telefono_alterno: Mapped[str | None]
    user_id: Mapped[uuid.UUID | None]
    autoriza_datos_at: Mapped[datetime | None]
    notas: Mapped[str | None]
    activa: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(**_DB)
    updated_at: Mapped[datetime] = mapped_column(**_DB_ALWAYS)


class UnidadPersona(UUIDPk, Base):
    __tablename__ = "unidad_personas"
    __mapper_args__ = _EAGER

    tenant_id: Mapped[uuid.UUID]
    unidad_id: Mapped[uuid.UUID]
    persona_id: Mapped[uuid.UUID]
    relacion: Mapped[RelacionUnidad] = mapped_column(pg_enum(RelacionUnidad, "relacion_unidad"))
    porcentaje_propiedad: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    es_contacto_principal: Mapped[bool] = mapped_column(default=False)
    responsable_pago: Mapped[bool] = mapped_column(default=False)
    reside: Mapped[bool] = mapped_column(default=False)
    fecha_inicio: Mapped[date]
    fecha_fin: Mapped[date | None]
    motivo_cierre: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(**_DB)

    @property
    def vigente(self) -> bool:
        return self.fecha_fin is None


class Vehiculo(UUIDPk, Base):
    __tablename__ = "vehiculos"
    __mapper_args__ = _EAGER

    tenant_id: Mapped[uuid.UUID]
    unidad_id: Mapped[uuid.UUID]
    persona_id: Mapped[uuid.UUID | None]
    placa: Mapped[str]
    tipo: Mapped[TipoVehiculo] = mapped_column(pg_enum(TipoVehiculo, "tipo_vehiculo"), default=TipoVehiculo.CARRO)
    marca: Mapped[str | None]
    color: Mapped[str | None]
    activo: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(**_DB)
    updated_at: Mapped[datetime] = mapped_column(**_DB_ALWAYS)


class ImportacionUnidades(UUIDPk, Base):
    """Bitácora inmutable. Sin eager_defaults: el ADMIN la escribe y la lee, pero no
    hace falta releer la fila tras el INSERT."""

    __tablename__ = "importaciones_unidades"

    tenant_id: Mapped[uuid.UUID]
    usuario_id: Mapped[uuid.UUID | None]
    archivo_nombre: Mapped[str]
    sha256: Mapped[str]
    filas_leidas: Mapped[int] = mapped_column(default=0)
    unidades_creadas: Mapped[int] = mapped_column(default=0)
    unidades_actualizadas: Mapped[int] = mapped_column(default=0)
    personas_creadas: Mapped[int] = mapped_column(default=0)
    personas_actualizadas: Mapped[int] = mapped_column(default=0)
    vinculos_creados: Mapped[int] = mapped_column(default=0)
    vehiculos_creados: Mapped[int] = mapped_column(default=0)
    advertencias: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(**_DB)


class AuditoriaUnidad(Base):
    """Solo lectura para la aplicación: la escribe un trigger de la base de datos."""

    __tablename__ = "auditoria_unidades"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    entidad: Mapped[str]
    entidad_id: Mapped[uuid.UUID]
    unidad_id: Mapped[uuid.UUID | None]
    usuario_id: Mapped[uuid.UUID | None]
    accion: Mapped[AccionAuditoria] = mapped_column(pg_enum(AccionAuditoria, "accion_auditoria"))
    valores_anteriores: Mapped[dict[str, Any] | None]
    valores_nuevos: Mapped[dict[str, Any] | None]
    motivo: Mapped[str | None]
    fecha_hora: Mapped[datetime]
