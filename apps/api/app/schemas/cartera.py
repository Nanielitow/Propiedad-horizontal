"""Esquemas de entrada del módulo de cartera."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import MedioPago, MetodoCuota, TipoAjuste, TipoUnidad

Dinero = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]
Motivo = Annotated[str, Field(min_length=10, max_length=1000)]
Texto = Annotated[str, Field(min_length=1, max_length=300)]


class _Base(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class ConfigIn(_Base):
    metodo: MetodoCuota
    presupuesto_mensual: Dinero | None = None
    tarifas_por_tipo: dict[TipoUnidad, Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]] = {}
    redondeo: Literal[1, 10, 50, 100, 500, 1000] = 100
    dia_vencimiento: Annotated[int, Field(ge=1, le=28)] = 10
    descuento_pct: Annotated[Decimal, Field(ge=0, le=50, max_digits=5, decimal_places=2)] = Decimal(0)
    dia_limite_descuento: Annotated[int, Field(ge=1, le=28)] | None = None
    cobrar_intereses: bool = True
    tasa_mora_mensual: Annotated[Decimal, Field(ge=0, le=5, max_digits=6, decimal_places=4)] = Decimal("1.5")
    nota_cuenta_cobro: Annotated[str, Field(max_length=1000)] | None = None
    motivo: Annotated[str, Field(max_length=1000)] | None = None

    @model_validator(mode="after")
    def _coherente(self) -> "ConfigIn":
        if self.metodo == MetodoCuota.COEFICIENTE and self.presupuesto_mensual is None:
            raise ValueError("Con el método por coeficiente, indique el presupuesto mensual")
        if self.metodo == MetodoCuota.TARIFA_POR_TIPO and not any(v > 0 for v in self.tarifas_por_tipo.values()):
            raise ValueError("Indique la tarifa mensual de al menos un tipo de unidad")
        if self.descuento_pct > 0:
            if self.dia_limite_descuento is None:
                raise ValueError("Indique hasta qué día del mes aplica el descuento por pronto pago")
            if self.dia_limite_descuento > self.dia_vencimiento:
                raise ValueError("El día límite del descuento no puede ser posterior al vencimiento")
        return self


class EmitirPeriodoIn(_Base):
    anio: Annotated[int, Field(ge=2000, le=2100)]
    mes: Annotated[int, Field(ge=1, le=12)]
    fecha_emision: date | None = None


class CargoManualIn(_Base):
    """Cuota extraordinaria, multa u otro cobro. Para varias unidades o todas, con un valor
    por unidad o un total aprobado que se reparte por coeficiente, en una o varias cuotas."""

    concepto_id: uuid.UUID
    descripcion: Texto
    unidad_ids: Annotated[list[uuid.UUID], Field(max_length=5000)] = []  # vacío + todas=True: todas
    todas: bool = False
    modo: Literal["VALOR_POR_UNIDAD", "TOTAL_POR_COEFICIENTE"] = "VALOR_POR_UNIDAD"
    valor: Dinero
    numero_cuotas: Annotated[int, Field(ge=1, le=24)] = 1
    primer_vencimiento: date

    @model_validator(mode="after")
    def _destino(self) -> "CargoManualIn":
        if self.todas == bool(self.unidad_ids):
            raise ValueError("Elija unidades específicas o «todas», no ambas")
        if self.modo == "TOTAL_POR_COEFICIENTE" and not self.todas and len(self.unidad_ids) < 2:
            raise ValueError("Repartir por coeficiente tiene sentido entre varias unidades")
        return self


class PagoIn(_Base):
    unidad_id: uuid.UUID
    fecha_pago: date
    valor: Dinero
    medio_pago: MedioPago
    referencia: Annotated[str, Field(max_length=100)] | None = None
    pagador_nombre: Annotated[str, Field(max_length=200)] | None = None
    soporte_key: Annotated[str, Field(max_length=500)] | None = None
    observaciones: Annotated[str, Field(max_length=1000)] | None = None

    @field_validator("referencia")
    @classmethod
    def _referencia(cls, v: str | None) -> str | None:
        return " ".join(v.split()).upper() or None if v else None

    @model_validator(mode="after")
    def _soporte(self) -> "PagoIn":
        if self.medio_pago != MedioPago.EFECTIVO and not (self.referencia or self.soporte_key):
            raise ValueError("Para transferencias y consignaciones indique la referencia o adjunte el soporte")
        return self


class AjusteIn(_Base):
    cargo_id: uuid.UUID
    tipo: Literal[TipoAjuste.CONDONACION, TipoAjuste.CORRECCION]
    valor: Dinero
    motivo: Motivo


class AnularIn(_Base):
    motivo: Motivo


class ConciliacionItemIn(_Base):
    """Un movimiento del extracto confirmado por la administración para registrarlo como pago."""

    fila: Annotated[int, Field(ge=1)]
    unidad_id: uuid.UUID
    fecha_pago: date
    valor: Dinero
    medio_pago: MedioPago
    referencia: Annotated[str, Field(min_length=4, max_length=100)]
    pagador_nombre: Annotated[str, Field(max_length=200)] | None = None


class ConciliacionIn(_Base):
    items: Annotated[list[ConciliacionItemIn], Field(min_length=1, max_length=500)]
