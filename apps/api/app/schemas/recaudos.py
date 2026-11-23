"""Esquemas de entrada del módulo de recaudos.

Validan la FORMA de los datos (tipos, montos positivos, placa). Las reglas que
dependen del concepto (vehículo, reserva, tarifa) las aplica el servicio.
"""

import re
import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import EstadoReserva, MedioPago, TipoCobro

Monto = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]
TextoCorto = Annotated[str, Field(min_length=1, max_length=200)]
Motivo = Annotated[str, Field(min_length=10, max_length=1000)]

_PLACA = re.compile(r"^[A-Z0-9]{5,7}$")


def normalizar_placa(valor: str) -> str:
    """'abc-123' / ' ABC 123 ' -> 'ABC123'. Rechaza lo que no parezca una placa."""
    placa = re.sub(r"[\s\-.]", "", valor).upper()
    if not _PLACA.fullmatch(placa):
        raise ValueError("Placa inválida: use 5 a 7 letras o números (p. ej. ABC123 o ABC12D)")
    return placa


class _Base(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class ParqueaderoIn(_Base):
    placa_vehiculo: str
    hora_ingreso: datetime
    hora_salida: datetime

    @field_validator("placa_vehiculo")
    @classmethod
    def _placa(cls, v: str) -> str:
        return normalizar_placa(v)

    @field_validator("hora_ingreso", "hora_salida")
    @classmethod
    def _con_zona(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("La hora debe incluir zona horaria")
        return v

    @model_validator(mode="after")
    def _orden(self) -> "ParqueaderoIn":
        if self.hora_salida <= self.hora_ingreso:
            raise ValueError("La hora de salida debe ser posterior a la de ingreso")
        return self


class ItemIn(_Base):
    concepto_id: uuid.UUID
    valor: Monto
    descripcion: Annotated[str, Field(max_length=200)] | None = None


class RecaudoCreate(_Base):
    concepto_id: uuid.UUID
    medio_pago: MedioPago
    nombre_pagador: Annotated[str, Field(min_length=2, max_length=200)]
    # Si se omite: tarifa del concepto (fijo), cálculo por tiempo (parqueadero) o suma del desglose
    valor_recibido: Monto | None = None
    identificacion_pagador: Annotated[str, Field(max_length=30)] | None = None
    unidad_id: uuid.UUID | None = None
    fecha_recaudo: datetime | None = None
    numero_comprobante: Annotated[str, Field(max_length=60)] | None = None
    soporte_key: Annotated[str, Field(max_length=500)] | None = None
    observaciones: Annotated[str, Field(max_length=1000)] | None = None
    parqueadero: ParqueaderoIn | None = None
    reserva_id: uuid.UUID | None = None
    # Varias líneas en una misma transacción (p. ej. alquiler + aseo)
    desglose: Annotated[list[ItemIn], Field(min_length=1, max_length=10)] | None = None


class RecaudoUpdate(_Base):
    """Solo campos descriptivos: concepto, valor, medio, fecha y receptor no se editan (se anula)."""

    nombre_pagador: Annotated[str, Field(min_length=2, max_length=200)] | None = None
    identificacion_pagador: Annotated[str, Field(max_length=30)] | None = None
    unidad_id: uuid.UUID | None = None
    numero_comprobante: Annotated[str, Field(max_length=60)] | None = None
    soporte_key: Annotated[str, Field(max_length=500)] | None = None
    observaciones: Annotated[str, Field(max_length=1000)] | None = None
    motivo: Annotated[str, Field(min_length=5, max_length=1000)]


class AnulacionIn(_Base):
    motivo: Motivo


class CotizacionParqueadero(BaseModel):
    minutos: int
    fracciones: int
    tarifa_sugerida: Decimal


# --- Fase 2: caja, entregas, consignaciones y alertas -----------------------

MontoNoNegativo = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]


class CierreCajaIn(_Base):
    saldo_inicial: MontoNoNegativo = Decimal(0)
    valor_fisico_contado: MontoNoNegativo
    observacion_justificacion: Annotated[str, Field(max_length=1000)] | None = None


class EntregaCreate(_Base):
    recibido_por_id: uuid.UUID
    recaudo_ids: Annotated[list[uuid.UUID], Field(min_length=1, max_length=500)]
    observaciones: Annotated[str, Field(max_length=1000)] | None = None

    @field_validator("recaudo_ids")
    @classmethod
    def _sin_repetidos(cls, v: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(set(v)) != len(v):
            raise ValueError("Hay recaudos repetidos")
        return v


class EntregaConfirmacion(_Base):
    valor_contado: MontoNoNegativo
    observaciones: Annotated[str, Field(max_length=1000)] | None = None


class AplicacionIn(_Base):
    recaudo_id: uuid.UUID
    valor_aplicado: Monto | None = None  # si se omite: todo el saldo pendiente del recaudo


class ConsignacionCreate(_Base):
    fecha_consignacion: date
    banco_destino: TextoCorto
    referencia_bancaria: Annotated[str, Field(min_length=3, max_length=60)]
    valor_consignado: Monto
    soporte_bancario_key: Annotated[str, Field(max_length=500)] | None = None
    observaciones: Annotated[str, Field(max_length=1000)] | None = None
    aplicaciones: Annotated[list[AplicacionIn], Field(min_length=1, max_length=500)]

    @field_validator("aplicaciones")
    @classmethod
    def _sin_repetidos(cls, v: list[AplicacionIn]) -> list[AplicacionIn]:
        if len({a.recaudo_id for a in v}) != len(v):
            raise ValueError("Hay recaudos repetidos")
        return v


class RechazoIn(_Base):
    motivo: Motivo


class AtencionAlertaIn(_Base):
    resolucion: Annotated[str, Field(min_length=5, max_length=1000)]


# --- Catálogos (fase 3) ---------------------------------------------------------

Tarifa = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]


class ConceptoCreate(_Base):
    codigo: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{1,39}$")]
    nombre: Annotated[str, Field(min_length=2, max_length=120)]
    descripcion: Annotated[str, Field(max_length=500)] | None = None
    tipo_cobro: TipoCobro
    tarifa_base: Tarifa | None = None
    fraccion_minutos: Annotated[int, Field(ge=1, le=1440)] | None = None
    requiere_reserva: bool = False
    requiere_vehiculo: bool = False

    @model_validator(mode="after")
    def _coherente(self) -> "ConceptoCreate":
        if self.tipo_cobro == TipoCobro.POR_HORA and (self.tarifa_base is None or self.fraccion_minutos is None):
            raise ValueError("Un cobro por hora necesita tarifa y fracción en minutos")
        if self.tipo_cobro == TipoCobro.FIJO and self.tarifa_base is None:
            raise ValueError("Un cobro fijo necesita tarifa")
        return self


class ConceptoUpdate(_Base):
    """El código no cambia: el sistema se apoya en él (p. ej. ASEO en el desglose de alquileres)."""

    nombre: Annotated[str, Field(min_length=2, max_length=120)] | None = None
    descripcion: Annotated[str, Field(max_length=500)] | None = None
    tipo_cobro: TipoCobro | None = None
    tarifa_base: Tarifa | None = None
    fraccion_minutos: Annotated[int, Field(ge=1, le=1440)] | None = None
    requiere_reserva: bool | None = None
    requiere_vehiculo: bool | None = None
    activo: bool | None = None


class ZonaCreate(_Base):
    nombre: Annotated[str, Field(min_length=2, max_length=120)]
    tarifa_alquiler: Tarifa | None = None
    tarifa_aseo: Tarifa | None = None


class ZonaUpdate(_Base):
    nombre: Annotated[str, Field(min_length=2, max_length=120)] | None = None
    tarifa_alquiler: Tarifa | None = None
    tarifa_aseo: Tarifa | None = None
    activo: bool | None = None


class ReservaCreate(_Base):
    zona_id: uuid.UUID
    solicitante: Annotated[str, Field(min_length=2, max_length=200)]
    fecha_evento: date
    unidad_id: uuid.UUID | None = None
    hora_inicio: time | None = None
    hora_fin: time | None = None
    observaciones: Annotated[str, Field(max_length=1000)] | None = None

    @model_validator(mode="after")
    def _horas(self) -> "ReservaCreate":
        if self.hora_inicio and self.hora_fin and self.hora_fin <= self.hora_inicio:
            raise ValueError("La hora de fin debe ser posterior a la de inicio")
        return self


class ReservaUpdate(_Base):
    estado: EstadoReserva | None = None
    fecha_evento: date | None = None
    hora_inicio: time | None = None
    hora_fin: time | None = None
    observaciones: Annotated[str, Field(max_length=1000)] | None = None


class SoporteUploadIn(_Base):
    content_type: str
    size_bytes: Annotated[int, Field(gt=0)]
