"""Módulo de recaudos e ingresos extraordinarios (migración 0003, docs/RECAUDOS.md).

Las columnas que asigna la base de datos (consecutivo y estado inicial por
trigger, columnas generadas, fechas) se declaran con FetchedValue y
eager_defaults: tras el INSERT el ORM las lee con RETURNING.
"""

import uuid
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import FetchedValue, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPk
from app.models.enums import (
    AccionAuditoria,
    EstadoAlerta,
    EstadoConsignacion,
    EstadoEntrega,
    EstadoRecaudo,
    EstadoReserva,
    MedioPago,
    SeveridadAlerta,
    TipoAlerta,
    TipoCobro,
    pg_enum,
)

Money = Numeric(14, 2)
_DB = {"server_default": FetchedValue()}  # lo asigna la base de datos al insertar
_DB_ALWAYS = {"server_default": FetchedValue(), "server_onupdate": FetchedValue()}
_EAGER = {"eager_defaults": True}


class ConceptoRecaudo(UUIDPk, Base):
    __tablename__ = "conceptos_recaudo"
    __mapper_args__ = _EAGER

    tenant_id: Mapped[uuid.UUID]
    codigo: Mapped[str]
    nombre: Mapped[str]
    descripcion: Mapped[str | None]
    tarifa_base: Mapped[Decimal | None] = mapped_column(Money)
    tipo_cobro: Mapped[TipoCobro] = mapped_column(pg_enum(TipoCobro, "tipo_cobro"))
    fraccion_minutos: Mapped[int | None]
    requiere_reserva: Mapped[bool] = mapped_column(default=False)
    requiere_vehiculo: Mapped[bool] = mapped_column(default=False)
    activo: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(**_DB)
    updated_at: Mapped[datetime] = mapped_column(**_DB_ALWAYS)


class ZonaSocial(UUIDPk, Base):
    __tablename__ = "zonas_sociales"
    __mapper_args__ = _EAGER

    tenant_id: Mapped[uuid.UUID]
    nombre: Mapped[str]
    tarifa_alquiler: Mapped[Decimal | None] = mapped_column(Money)
    tarifa_aseo: Mapped[Decimal | None] = mapped_column(Money)
    activo: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(**_DB)
    # Reglas para reservar desde el portal del residente (migración 0009)
    descripcion: Mapped[str | None]
    capacidad: Mapped[int | None]
    reglas: Mapped[str | None]
    hora_apertura: Mapped[time] = mapped_column(**_DB)
    hora_cierre: Mapped[time] = mapped_column(**_DB)
    anticipacion_min_dias: Mapped[int] = mapped_column(**_DB)
    anticipacion_max_dias: Mapped[int] = mapped_column(**_DB)
    max_reservas_mes_unidad: Mapped[int] = mapped_column(**_DB)
    requiere_paz_y_salvo: Mapped[bool] = mapped_column(**_DB)
    requiere_aprobacion: Mapped[bool] = mapped_column(**_DB)
    reservable_residentes: Mapped[bool] = mapped_column(**_DB)


class Reserva(UUIDPk, Base):
    __tablename__ = "reservas"
    __mapper_args__ = _EAGER

    tenant_id: Mapped[uuid.UUID]
    zona_id: Mapped[uuid.UUID]
    unidad_id: Mapped[uuid.UUID | None]
    solicitante: Mapped[str]
    fecha_evento: Mapped[date]
    hora_inicio: Mapped[time | None]
    hora_fin: Mapped[time | None]
    estado: Mapped[EstadoReserva] = mapped_column(
        pg_enum(EstadoReserva, "estado_reserva"), default=EstadoReserva.SOLICITADA
    )
    observaciones: Mapped[str | None]
    creado_por_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(**_DB)
    # Portal del residente (migración 0009)
    numero_asistentes: Mapped[int | None]
    solicitada_en_portal: Mapped[bool] = mapped_column(default=False)
    decidida_por_id: Mapped[uuid.UUID | None]
    decidida_at: Mapped[datetime | None]
    motivo_decision: Mapped[str | None]
    updated_at: Mapped[datetime] = mapped_column(server_default=FetchedValue(), server_onupdate=FetchedValue())


class Recaudo(UUIDPk, Base):
    __tablename__ = "recaudos"
    __mapper_args__ = _EAGER

    tenant_id: Mapped[uuid.UUID]
    consecutivo: Mapped[int] = mapped_column(**_DB)  # trigger: sin huecos por copropiedad
    fecha_recaudo: Mapped[datetime]
    concepto_id: Mapped[uuid.UUID]
    valor_recibido: Mapped[Decimal] = mapped_column(Money)
    nombre_pagador: Mapped[str]
    identificacion_pagador: Mapped[str | None]
    unidad_id: Mapped[uuid.UUID | None]
    medio_pago: Mapped[MedioPago] = mapped_column(pg_enum(MedioPago, "medio_pago"))
    # Estado inicial lo fija el trigger según el medio de pago
    estado: Mapped[EstadoRecaudo] = mapped_column(pg_enum(EstadoRecaudo, "estado_recaudo"), **_DB)
    numero_comprobante: Mapped[str | None]
    soporte_key: Mapped[str | None]
    observaciones: Mapped[str | None]
    reserva_id: Mapped[uuid.UUID | None]
    usuario_receptor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    cierre_id: Mapped[uuid.UUID | None]
    entrega_id: Mapped[uuid.UUID | None]
    anulado_por_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    anulado_at: Mapped[datetime | None]
    motivo_anulacion: Mapped[str | None]
    verificado_por_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    verificado_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(**_DB)
    updated_at: Mapped[datetime] = mapped_column(**_DB_ALWAYS)


class RecaudoItem(UUIDPk, Base):
    __tablename__ = "recaudo_items"

    tenant_id: Mapped[uuid.UUID]
    recaudo_id: Mapped[uuid.UUID]
    concepto_id: Mapped[uuid.UUID]
    descripcion: Mapped[str | None]
    valor: Mapped[Decimal] = mapped_column(Money)


class RecaudoParqueadero(Base):
    __tablename__ = "recaudo_parqueadero"
    __mapper_args__ = _EAGER

    recaudo_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    placa_vehiculo: Mapped[str]
    hora_ingreso: Mapped[datetime]
    hora_salida: Mapped[datetime]
    minutos_totales: Mapped[int] = mapped_column(**_DB)  # columna generada
    tarifa_sugerida: Mapped[Decimal] = mapped_column(Money)


class CierreCaja(UUIDPk, Base):
    __tablename__ = "cierres_caja"
    __mapper_args__ = _EAGER

    tenant_id: Mapped[uuid.UUID]
    consecutivo: Mapped[int] = mapped_column(**_DB)
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    inicio_turno: Mapped[datetime]
    fin_turno: Mapped[datetime] = mapped_column(**_DB)
    saldo_inicial: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    saldo_esperado_sistema: Mapped[Decimal] = mapped_column(Money)
    valor_fisico_contado: Mapped[Decimal] = mapped_column(Money)
    diferencia: Mapped[Decimal] = mapped_column(Money, **_DB)  # generada
    tipo_diferencia: Mapped[str] = mapped_column(**_DB)  # generada: CUADRADO/SOBRANTE/FALTANTE
    observacion_justificacion: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(**_DB)


class EntregaInterna(UUIDPk, Base):
    __tablename__ = "entregas_internas"
    __mapper_args__ = _EAGER

    tenant_id: Mapped[uuid.UUID]
    consecutivo: Mapped[int] = mapped_column(**_DB)
    entregado_por_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    recibido_por_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    fecha_entrega: Mapped[datetime] = mapped_column(**_DB)
    valor_total: Mapped[Decimal] = mapped_column(Money)
    estado: Mapped[EstadoEntrega] = mapped_column(
        pg_enum(EstadoEntrega, "estado_entrega"), default=EstadoEntrega.PENDIENTE_CONFIRMACION
    )
    valor_contado: Mapped[Decimal | None] = mapped_column(Money)
    confirmada_at: Mapped[datetime | None]
    observaciones: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(**_DB)
    updated_at: Mapped[datetime] = mapped_column(**_DB_ALWAYS)


class Consignacion(UUIDPk, Base):
    __tablename__ = "consignaciones"
    __mapper_args__ = _EAGER

    tenant_id: Mapped[uuid.UUID]
    consecutivo: Mapped[int] = mapped_column(**_DB)
    fecha_consignacion: Mapped[date]
    banco_destino: Mapped[str]
    referencia_bancaria: Mapped[str]
    valor_consignado: Mapped[Decimal] = mapped_column(Money)
    soporte_bancario_key: Mapped[str | None]
    usuario_consigna_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    estado: Mapped[EstadoConsignacion] = mapped_column(
        pg_enum(EstadoConsignacion, "estado_consignacion"), default=EstadoConsignacion.REGISTRADA
    )
    aprobada_por_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    aprobada_at: Mapped[datetime | None]
    verificada_por_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    verificada_at: Mapped[datetime | None]
    observaciones: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(**_DB)
    updated_at: Mapped[datetime] = mapped_column(**_DB_ALWAYS)


class ConsignacionRecaudo(Base):
    __tablename__ = "consignacion_recaudos"

    consignacion_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    recaudo_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    valor_aplicado: Mapped[Decimal] = mapped_column(Money)


class AuditoriaRecaudo(Base):
    """Solo lectura para la aplicación: la escribe un trigger de la base de datos."""

    __tablename__ = "auditoria_recaudos"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    entidad: Mapped[str]
    entidad_id: Mapped[uuid.UUID]
    recaudo_id: Mapped[uuid.UUID | None]
    usuario_id: Mapped[uuid.UUID | None]
    accion: Mapped[AccionAuditoria] = mapped_column(pg_enum(AccionAuditoria, "accion_auditoria"))
    valores_anteriores: Mapped[dict[str, Any] | None]
    valores_nuevos: Mapped[dict[str, Any] | None]
    motivo: Mapped[str | None]
    fecha_hora: Mapped[datetime]


class AlertaRecaudo(UUIDPk, Base):
    """Sin RETURNING: el auxiliar puede CREAR alertas (p. ej. su cierre con faltante) pero no
    leerlas, y PostgreSQL exige permiso de lectura para devolver columnas tras el INSERT."""

    __tablename__ = "alertas_recaudo"

    tenant_id: Mapped[uuid.UUID]
    tipo: Mapped[TipoAlerta] = mapped_column(pg_enum(TipoAlerta, "tipo_alerta"))
    severidad: Mapped[SeveridadAlerta] = mapped_column(
        pg_enum(SeveridadAlerta, "severidad_alerta"), default=SeveridadAlerta.ADVERTENCIA
    )
    entidad: Mapped[str]
    entidad_id: Mapped[uuid.UUID]
    mensaje: Mapped[str]
    monto: Mapped[Decimal | None] = mapped_column(Money)
    estado: Mapped[EstadoAlerta] = mapped_column(pg_enum(EstadoAlerta, "estado_alerta"), default=EstadoAlerta.ABIERTA)
    atendida_por_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    atendida_at: Mapped[datetime | None]
    resolucion: Mapped[str | None]
    notificada_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))


class CorteMensual(UUIDPk, Base):
    __tablename__ = "cortes_mensuales"
    __mapper_args__ = _EAGER

    tenant_id: Mapped[uuid.UUID]
    periodo: Mapped[date]
    resumen: Mapped[dict[str, Any]]
    pdf_key: Mapped[str | None]
    xlsx_key: Mapped[str | None]
    generado_at: Mapped[datetime] = mapped_column(**_DB)
