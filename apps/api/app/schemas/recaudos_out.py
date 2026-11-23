"""Respuestas de la API de recaudos."""

import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

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
    UserRole,
)


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ConceptoOut(_Out):
    id: uuid.UUID
    codigo: str
    nombre: str
    descripcion: str | None
    tipo_cobro: TipoCobro
    tarifa_base: Decimal | None
    fraccion_minutos: int | None
    requiere_reserva: bool
    requiere_vehiculo: bool
    activo: bool


class ZonaOut(_Out):
    id: uuid.UUID
    nombre: str
    tarifa_alquiler: Decimal | None
    tarifa_aseo: Decimal | None
    activo: bool


class ReservaOut(_Out):
    id: uuid.UUID
    zona_id: uuid.UUID
    unidad_id: uuid.UUID | None
    solicitante: str
    fecha_evento: date
    hora_inicio: time | None
    hora_fin: time | None
    estado: EstadoReserva
    observaciones: str | None


class PersonaOut(_Out):
    id: uuid.UUID
    nombre: str
    rol: UserRole


class UnidadOut(BaseModel):
    id: uuid.UUID
    etiqueta: str  # "Torre 2 · 502"


class SoporteUploadOut(BaseModel):
    soporte_key: str
    upload_url: str
    headers: dict[str, str]
    expires_in: int


# --- Recaudos --------------------------------------------------------------------


class RecaudoFila(BaseModel):
    id: uuid.UUID
    consecutivo: int
    fecha_recaudo: datetime
    concepto_id: uuid.UUID
    concepto: str
    valor_recibido: Decimal
    nombre_pagador: str
    identificacion_pagador: str | None
    unidad_id: uuid.UUID | None
    unidad: str | None
    medio_pago: MedioPago
    estado: EstadoRecaudo
    numero_comprobante: str | None
    usuario_receptor_id: uuid.UUID
    receptor: str
    placa: str | None
    tiene_soporte: bool
    cierre_id: uuid.UUID | None
    entrega_id: uuid.UUID | None


class RecaudosPagina(BaseModel):
    items: list[RecaudoFila]
    total: int  # filas que cumplen el filtro
    suma: Decimal  # valor de esas filas sin contar las anuladas
    page: int
    page_size: int


class ItemOut(BaseModel):
    concepto_id: uuid.UUID
    concepto: str
    descripcion: str | None
    valor: Decimal


class ParqueaderoOut(_Out):
    placa_vehiculo: str
    hora_ingreso: datetime
    hora_salida: datetime
    minutos_totales: int
    tarifa_sugerida: Decimal


class AplicacionOut(BaseModel):
    consignacion_id: uuid.UUID
    consecutivo: int
    banco_destino: str
    referencia_bancaria: str
    estado: EstadoConsignacion
    valor_aplicado: Decimal


class RecaudoDetalle(RecaudoFila):
    observaciones: str | None
    items: list[ItemOut]
    parqueadero: ParqueaderoOut | None
    reserva: ReservaOut | None
    zona: str | None
    consignaciones: list[AplicacionOut]
    saldo_por_consignar: Decimal
    soporte_url: str | None
    anulado_por: str | None
    anulado_at: datetime | None
    motivo_anulacion: str | None
    verificado_por: str | None
    verificado_at: datetime | None


class AuditoriaOut(BaseModel):
    id: int
    entidad: str
    accion: AccionAuditoria
    usuario: str | None
    fecha_hora: datetime
    valores_anteriores: dict[str, Any] | None
    valores_nuevos: dict[str, Any] | None
    motivo: str | None


class CotizacionOut(BaseModel):
    minutos: int
    fracciones: int
    tarifa_sugerida: Decimal


# --- Caja --------------------------------------------------------------------------


class ResumenCajaOut(BaseModel):
    inicio_turno: datetime
    cantidad: int
    total_efectivo: Decimal
    recaudos: list[RecaudoFila]


class CierreOut(BaseModel):
    id: uuid.UUID
    consecutivo: int
    usuario_id: uuid.UUID
    usuario: str
    inicio_turno: datetime
    fin_turno: datetime
    saldo_inicial: Decimal
    saldo_esperado_sistema: Decimal
    valor_fisico_contado: Decimal
    diferencia: Decimal
    tipo_diferencia: str
    observacion_justificacion: str | None
    cantidad_recaudos: int


class CierreDetalle(CierreOut):
    recaudos: list[RecaudoFila]


class EntregaOut(BaseModel):
    id: uuid.UUID
    consecutivo: int
    entregado_por_id: uuid.UUID
    entregado_por: str
    recibido_por_id: uuid.UUID
    recibido_por: str
    fecha_entrega: datetime
    valor_total: Decimal
    valor_contado: Decimal | None
    estado: EstadoEntrega
    confirmada_at: datetime | None
    observaciones: str | None
    cantidad_recaudos: int


class EntregaDetalle(EntregaOut):
    recaudos: list[RecaudoFila]


class PendienteOut(BaseModel):
    recaudo: RecaudoFila
    saldo: Decimal


class ConsignacionOut(BaseModel):
    id: uuid.UUID
    consecutivo: int
    fecha_consignacion: date
    banco_destino: str
    referencia_bancaria: str
    valor_consignado: Decimal
    valor_aplicado: Decimal
    usuario_consigna_id: uuid.UUID
    usuario_consigna: str
    estado: EstadoConsignacion
    aprobada_at: datetime | None
    verificada_at: datetime | None
    observaciones: str | None
    cantidad_recaudos: int


class AplicacionDetalle(BaseModel):
    recaudo: RecaudoFila
    valor_aplicado: Decimal


class ConsignacionDetalle(ConsignacionOut):
    aplicaciones: list[AplicacionDetalle]
    soporte_url: str | None
    aprobada_por: str | None
    verificada_por: str | None


class ResultadoConsignacion(BaseModel):
    consignacion: ConsignacionOut
    recaudos_actualizados: list[uuid.UUID]  # pasaron a CONSIGNADO o VERIFICADO


# --- Alertas y dashboard -----------------------------------------------------------


class AlertaOut(_Out):
    id: uuid.UUID
    tipo: TipoAlerta
    severidad: SeveridadAlerta
    entidad: str
    entidad_id: uuid.UUID
    mensaje: str
    monto: Decimal | None
    estado: EstadoAlerta
    atendida_at: datetime | None
    resolucion: str | None
    created_at: datetime


class ConceptoTotal(BaseModel):
    codigo: str
    concepto: str
    total: Decimal


class DiaTotal(BaseModel):
    dia: date
    total: Decimal


class TransferenciasPendientes(BaseModel):
    cantidad: int
    total: Decimal


class DashboardOut(BaseModel):
    periodo: str
    total_mes: Decimal
    cantidad_mes: int
    total_anio: Decimal
    por_concepto: list[ConceptoTotal]
    por_medio: dict[MedioPago, Decimal]
    por_estado: dict[EstadoRecaudo, Decimal]
    serie_diaria: list[DiaTotal]
    efectivo_en_caja: Decimal
    efectivo_en_administracion: Decimal
    transferencias_pendientes: TransferenciasPendientes
    alertas_abiertas: int
