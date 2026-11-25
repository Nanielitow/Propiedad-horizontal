"""Esquemas de salida del módulo de cartera."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.enums import (
    EstadoCargo,
    EstadoPagoCartera,
    EstadoPeriodo,
    MedioPago,
    MetodoCuota,
    TipoAjuste,
    TipoConceptoCartera,
)


class _Orm(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ConfigOut(_Orm):
    metodo: MetodoCuota
    presupuesto_mensual: Decimal | None
    tarifas_por_tipo: dict[str, Decimal]
    redondeo: int
    dia_vencimiento: int
    descuento_pct: Decimal
    dia_limite_descuento: int | None
    cobrar_intereses: bool
    tasa_mora_mensual: Decimal
    nota_cuenta_cobro: str | None
    updated_at: datetime


class ConceptoOut(_Orm):
    id: uuid.UUID
    codigo: str
    nombre: str
    tipo: TipoConceptoCartera
    genera_interes: bool
    activo: bool


class PeriodoOut(_Orm):
    id: uuid.UUID
    anio: int
    mes: int
    nombre: str
    estado: EstadoPeriodo
    fecha_emision: date
    fecha_vencimiento: date
    fecha_limite_descuento: date | None
    metodo: MetodoCuota
    presupuesto_mensual: Decimal | None
    descuento_pct: Decimal
    tasa_mora_mensual: Decimal | None
    unidades_facturadas: int
    total_cuotas: Decimal
    total_intereses: Decimal
    recaudado: Decimal  # lo aplicado a los cargos del periodo
    pendiente: Decimal
    advertencias: list[str]
    motivo_anulacion: str | None


class LineaPrefactura(BaseModel):
    unidad_id: uuid.UUID
    etiqueta: str
    responsable: str | None
    cuota: Decimal | None
    capital_vencido: Decimal
    interes: Decimal


class PrefacturaOut(BaseModel):
    anio: int
    mes: int
    nombre: str
    fecha_emision: date
    fecha_vencimiento: date
    fecha_limite_descuento: date | None
    metodo: MetodoCuota
    total_cuotas: Decimal
    total_intereses: Decimal
    unidades: int
    lineas: list[LineaPrefactura]
    advertencias: list[str]


class CargoOut(BaseModel):
    id: uuid.UUID
    unidad_id: uuid.UUID
    unidad: str
    concepto: str
    tipo_concepto: TipoConceptoCartera
    descripcion: str
    valor: Decimal
    saldo: Decimal
    fecha_causacion: date
    fecha_vencimiento: date
    dias_mora: int
    responsable_nombre: str | None
    estado: EstadoCargo
    periodo_id: uuid.UUID | None


class PagoOut(BaseModel):
    id: uuid.UUID
    consecutivo: int
    unidad_id: uuid.UUID
    unidad: str
    fecha_pago: date
    valor: Decimal
    aplicado: Decimal
    a_favor: Decimal
    descuentos: Decimal
    medio_pago: MedioPago
    referencia: str | None
    pagador_nombre: str | None
    tiene_soporte: bool
    observaciones: str | None
    estado: EstadoPagoCartera
    registrado_por: str | None
    created_at: datetime
    motivo_anulacion: str | None


class PagosPagina(BaseModel):
    items: list[PagoOut]
    total: int
    total_valor: Decimal
    page: int
    page_size: int


class AplicacionOut(BaseModel):
    cargo_id: uuid.UUID
    descripcion: str
    valor: Decimal
    descuento: Decimal


class ResultadoPagoOut(BaseModel):
    pago: PagoOut
    aplicaciones: list[AplicacionOut]
    a_favor: Decimal
    saldo_pendiente: Decimal


class Movimiento(BaseModel):
    fecha: date
    tipo: str  # CARGO, PAGO, AJUSTE
    descripcion: str
    cargo: Decimal  # débito
    abono: Decimal  # crédito
    saldo: Decimal  # acumulado
    anulado: bool
    referencia_id: uuid.UUID
    consecutivo: int | None = None


class EstadoCuenta(BaseModel):
    unidad_id: uuid.UUID
    unidad: str
    responsable: str | None
    copropiedad: str
    corte: date
    saldo_total: Decimal
    saldo_vencido: Decimal
    saldo_corriente: Decimal
    saldo_a_favor: Decimal
    dias_mora: int
    edades: dict[str, Decimal]
    al_dia: bool
    pendientes: list[CargoOut]
    movimientos: list[Movimiento]
    ultimo_pago: date | None


class Moroso(BaseModel):
    unidad_id: uuid.UUID
    unidad: str
    responsable: str | None
    telefono: str | None
    saldo_total: Decimal
    saldo_vencido: Decimal
    edades: dict[str, Decimal]
    dias_mora: int
    cuotas_vencidas: int
    ultimo_pago: date | None


class MorososOut(BaseModel):
    corte: date
    items: list[Moroso]
    total_vencido: Decimal
    edades: dict[str, Decimal]


class ResumenCartera(BaseModel):
    corte: date
    configurada: bool
    cartera_total: Decimal
    cartera_vencida: Decimal
    saldo_a_favor: Decimal
    edades: dict[str, Decimal]
    unidades_en_mora: int
    unidades_al_dia: int
    unidades_facturadas: int
    facturado_mes: Decimal
    recaudado_mes: Decimal  # pagos del mes calendario
    recaudo_pct: Decimal | None  # lo aplicado al periodo del mes / lo facturado
    ultimos_periodos: list[PeriodoOut]
    recaudo_mensual: list[dict[str, object]]  # últimos 12 meses: facturado vs. recaudado


class AjusteOut(_Orm):
    id: uuid.UUID
    cargo_id: uuid.UUID
    tipo: TipoAjuste
    valor: Decimal
    motivo: str
    created_at: datetime


class PazYSalvoOut(_Orm):
    id: uuid.UUID
    consecutivo: int
    unidad_id: uuid.UUID
    fecha_emision: date
    valido_hasta: date
    titular_nombre: str | None
    codigo_verificacion: str
