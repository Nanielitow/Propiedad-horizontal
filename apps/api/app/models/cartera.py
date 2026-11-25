"""Cartera de cuotas de administración (migración 0008, docs/CARTERA.md).

El saldo de un cargo nunca se guarda: es valor − aplicaciones de pagos vigentes −
ajustes (vista v_saldos_cargo). Así un pago anulado devuelve el saldo solo.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import FetchedValue, Numeric
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPk
from app.models.enums import (
    AccionAuditoria,
    EstadoCargo,
    EstadoPagoCartera,
    EstadoPeriodo,
    MedioPago,
    MetodoCuota,
    TipoAjuste,
    TipoConceptoCartera,
    pg_enum,
)

Money = Numeric(14, 2)
_DB = {"server_default": FetchedValue()}
_DB_ALWAYS = {"server_default": FetchedValue(), "server_onupdate": FetchedValue()}
_EAGER = {"eager_defaults": True}


class CarteraConfig(Base):
    __tablename__ = "cartera_config"
    __mapper_args__ = _EAGER

    tenant_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    metodo: Mapped[MetodoCuota] = mapped_column(pg_enum(MetodoCuota, "metodo_cuota"), default=MetodoCuota.COEFICIENTE)
    presupuesto_mensual: Mapped[Decimal | None] = mapped_column(Money)
    tarifas_por_tipo: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    redondeo: Mapped[int] = mapped_column(default=100)
    dia_vencimiento: Mapped[int] = mapped_column(default=10)
    descuento_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal(0))
    dia_limite_descuento: Mapped[int | None]
    cobrar_intereses: Mapped[bool] = mapped_column(default=True)
    tasa_mora_mensual: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("1.5"))
    nota_cuenta_cobro: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(**_DB)
    updated_at: Mapped[datetime] = mapped_column(**_DB_ALWAYS)


class ConceptoCartera(UUIDPk, Base):
    __tablename__ = "conceptos_cartera"
    __mapper_args__ = _EAGER

    tenant_id: Mapped[uuid.UUID]
    codigo: Mapped[str]
    nombre: Mapped[str]
    tipo: Mapped[TipoConceptoCartera] = mapped_column(pg_enum(TipoConceptoCartera, "tipo_concepto_cartera"))
    genera_interes: Mapped[bool] = mapped_column(default=True)
    activo: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(**_DB)


class PeriodoCartera(UUIDPk, Base):
    __tablename__ = "periodos_cartera"
    __mapper_args__ = _EAGER

    tenant_id: Mapped[uuid.UUID]
    anio: Mapped[int]
    mes: Mapped[int]
    estado: Mapped[EstadoPeriodo] = mapped_column(
        pg_enum(EstadoPeriodo, "estado_periodo"), default=EstadoPeriodo.EMITIDO
    )
    fecha_emision: Mapped[date]
    fecha_vencimiento: Mapped[date]
    fecha_limite_descuento: Mapped[date | None]
    metodo: Mapped[MetodoCuota] = mapped_column(pg_enum(MetodoCuota, "metodo_cuota"))
    presupuesto_mensual: Mapped[Decimal | None] = mapped_column(Money)
    descuento_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal(0))
    tasa_mora_mensual: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    unidades_facturadas: Mapped[int] = mapped_column(default=0)
    total_cuotas: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    total_intereses: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    advertencias: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    emitido_por_id: Mapped[uuid.UUID | None]
    anulado_por_id: Mapped[uuid.UUID | None]
    anulado_at: Mapped[datetime | None]
    motivo_anulacion: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(**_DB)


class CargoCartera(UUIDPk, Base):
    __tablename__ = "cargos_cartera"
    __mapper_args__ = _EAGER

    tenant_id: Mapped[uuid.UUID]
    unidad_id: Mapped[uuid.UUID]
    periodo_id: Mapped[uuid.UUID | None]
    concepto_id: Mapped[uuid.UUID]
    descripcion: Mapped[str]
    valor: Mapped[Decimal] = mapped_column(Money)
    fecha_causacion: Mapped[date]
    fecha_vencimiento: Mapped[date]
    genera_interes: Mapped[bool]
    descuento_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    fecha_limite_descuento: Mapped[date | None]
    responsable_persona_id: Mapped[uuid.UUID | None]
    responsable_nombre: Mapped[str | None]
    estado: Mapped[EstadoCargo] = mapped_column(pg_enum(EstadoCargo, "estado_cargo"), default=EstadoCargo.VIGENTE)
    anulado_por_id: Mapped[uuid.UUID | None]
    anulado_at: Mapped[datetime | None]
    motivo_anulacion: Mapped[str | None]
    creado_por_id: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime] = mapped_column(**_DB)


class PagoCartera(UUIDPk, Base):
    __tablename__ = "pagos_cartera"
    __mapper_args__ = _EAGER

    tenant_id: Mapped[uuid.UUID]
    consecutivo: Mapped[int] = mapped_column(**_DB)  # trigger: número de recibo sin huecos
    unidad_id: Mapped[uuid.UUID]
    fecha_pago: Mapped[date]
    valor: Mapped[Decimal] = mapped_column(Money)
    medio_pago: Mapped[MedioPago] = mapped_column(pg_enum(MedioPago, "medio_pago"))
    referencia: Mapped[str | None]
    pagador_nombre: Mapped[str | None]
    soporte_key: Mapped[str | None]
    observaciones: Mapped[str | None]
    estado: Mapped[EstadoPagoCartera] = mapped_column(
        pg_enum(EstadoPagoCartera, "estado_pago_cartera"), default=EstadoPagoCartera.APLICADO
    )
    registrado_por_id: Mapped[uuid.UUID]
    anulado_por_id: Mapped[uuid.UUID | None]
    anulado_at: Mapped[datetime | None]
    motivo_anulacion: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(**_DB)


class AplicacionPago(UUIDPk, Base):
    __tablename__ = "aplicaciones_pago"

    tenant_id: Mapped[uuid.UUID]
    pago_id: Mapped[uuid.UUID]
    cargo_id: Mapped[uuid.UUID]
    valor: Mapped[Decimal] = mapped_column(Money)
    created_at: Mapped[datetime] = mapped_column(**_DB)


class AjusteCartera(UUIDPk, Base):
    __tablename__ = "ajustes_cartera"

    tenant_id: Mapped[uuid.UUID]
    cargo_id: Mapped[uuid.UUID]
    tipo: Mapped[TipoAjuste] = mapped_column(pg_enum(TipoAjuste, "tipo_ajuste"))
    valor: Mapped[Decimal] = mapped_column(Money)
    motivo: Mapped[str]
    pago_id: Mapped[uuid.UUID | None]
    registrado_por_id: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime] = mapped_column(**_DB)


class PazYSalvo(UUIDPk, Base):
    __tablename__ = "paz_y_salvos"
    __mapper_args__ = _EAGER

    tenant_id: Mapped[uuid.UUID]
    consecutivo: Mapped[int] = mapped_column(**_DB)
    unidad_id: Mapped[uuid.UUID]
    fecha_emision: Mapped[date]
    valido_hasta: Mapped[date]
    titular_nombre: Mapped[str | None]
    codigo_verificacion: Mapped[str]
    emitido_por_id: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime] = mapped_column(**_DB)


class SaldoCargo(Base):
    """Vista v_saldos_cargo (solo lectura)."""

    __tablename__ = "v_saldos_cargo"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    unidad_id: Mapped[uuid.UUID]
    periodo_id: Mapped[uuid.UUID | None]
    concepto_id: Mapped[uuid.UUID]
    valor: Mapped[Decimal] = mapped_column(Money)
    fecha_causacion: Mapped[date]
    fecha_vencimiento: Mapped[date]
    genera_interes: Mapped[bool]
    estado: Mapped[EstadoCargo] = mapped_column(pg_enum(EstadoCargo, "estado_cargo"))
    aplicado: Mapped[Decimal] = mapped_column(Money)
    ajustado: Mapped[Decimal] = mapped_column(Money)
    saldo: Mapped[Decimal] = mapped_column(Money)


class AuditoriaCartera(Base):
    """Solo lectura para la aplicación: la escribe un trigger de la base de datos."""

    __tablename__ = "auditoria_cartera"

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
