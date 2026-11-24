"""Esquemas de entrada del módulo de unidades, copropietarios y residentes.

Validan la FORMA y normalizan (cédulas sin puntos, placas en mayúscula, torres
'Torre 2' -> '2'). Las reglas que dependen de la base (duplicados, unidad activa,
porcentajes de propiedad) están en app/services/unidades.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models.enums import OcupacionUnidad, RelacionUnidad, TipoDocumentoIdentidad, TipoUnidad, TipoVehiculo
from app.services.unidades import dominio as d

Texto = Annotated[str, Field(min_length=1, max_length=200)]
TextoLargo = Annotated[str, Field(max_length=4000)]
Motivo = Annotated[str, Field(min_length=10, max_length=1000)]
Coeficiente = Annotated[Decimal, Field(gt=0, le=100, max_digits=7, decimal_places=4)]
Area = Annotated[Decimal, Field(gt=0, max_digits=8, decimal_places=2)]
Porcentaje = Annotated[Decimal, Field(gt=0, le=100, max_digits=5, decimal_places=2)]


class _Base(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


# --- Unidades -------------------------------------------------------------------


class _UnidadCampos(_Base):
    @field_validator("tower", mode="before", check_fields=False)
    @classmethod
    def _torre(cls, v: str | None) -> str | None:
        return None if v is None else d.normalizar_torre(v)

    @field_validator("number", mode="before", check_fields=False)
    @classmethod
    def _numero(cls, v: str | int | None) -> str | None:
        return None if v is None else d.normalizar_numero(v)

    @field_validator("matricula_inmobiliaria", check_fields=False)
    @classmethod
    def _matricula(cls, v: str | None) -> str | None:
        return v.upper().replace(" ", "") or None if v else None


class UnidadIn(_UnidadCampos):
    tower: Annotated[str, Field(max_length=20)] = ""
    number: Annotated[str, Field(min_length=1, max_length=20)]
    tipo: TipoUnidad = TipoUnidad.APARTAMENTO
    coefficient: Coeficiente | None = None
    unidad_principal_id: uuid.UUID | None = None
    area_m2: Area | None = None
    matricula_inmobiliaria: Annotated[str, Field(max_length=40)] | None = None
    ocupacion: OcupacionUnidad = OcupacionUnidad.SIN_INFORMACION
    observaciones: TextoLargo | None = None


class UnidadUpdate(_UnidadCampos):
    tower: Annotated[str, Field(max_length=20)] | None = None
    number: Annotated[str, Field(min_length=1, max_length=20)] | None = None
    tipo: TipoUnidad | None = None
    coefficient: Coeficiente | None = None
    unidad_principal_id: uuid.UUID | None = None
    area_m2: Area | None = None
    matricula_inmobiliaria: Annotated[str, Field(max_length=40)] | None = None
    ocupacion: OcupacionUnidad | None = None
    observaciones: TextoLargo | None = None
    motivo: Annotated[str, Field(max_length=1000)] | None = None


class MotivoIn(_Base):
    motivo: Motivo


# --- Personas -------------------------------------------------------------------


class _PersonaCampos(_Base):
    @field_validator("numero_documento", check_fields=False)
    @classmethod
    def _documento(cls, v: str | None) -> str | None:
        return d.normalizar_documento(v) if v else None

    @field_validator("nombre_completo", check_fields=False)
    @classmethod
    def _nombre(cls, v: str | None) -> str | None:
        return None if v is None else d.normalizar_nombre(v)

    @field_validator("telefono", "telefono_alterno", check_fields=False)
    @classmethod
    def _telefono(cls, v: str | None) -> str | None:
        return d.normalizar_telefono(v) if v else None


class PersonaIn(_PersonaCampos):
    tipo_documento: TipoDocumentoIdentidad | None = None
    numero_documento: Annotated[str, Field(max_length=30)] | None = None
    nombre_completo: Annotated[str, Field(min_length=2, max_length=200)]
    email: EmailStr | None = None
    telefono: Annotated[str, Field(max_length=30)] | None = None
    telefono_alterno: Annotated[str, Field(max_length=30)] | None = None
    user_id: uuid.UUID | None = None
    autoriza_datos: bool = False
    notas: TextoLargo | None = None

    @model_validator(mode="after")
    def _documento_completo(self) -> "PersonaIn":
        if (self.tipo_documento is None) != (self.numero_documento is None):
            raise ValueError("Indique el tipo y el número de documento, o ninguno de los dos")
        return self


class PersonaUpdate(_PersonaCampos):
    tipo_documento: TipoDocumentoIdentidad | None = None
    numero_documento: Annotated[str, Field(max_length=30)] | None = None
    nombre_completo: Annotated[str, Field(min_length=2, max_length=200)] | None = None
    email: EmailStr | None = None
    telefono: Annotated[str, Field(max_length=30)] | None = None
    telefono_alterno: Annotated[str, Field(max_length=30)] | None = None
    user_id: uuid.UUID | None = None
    autoriza_datos: bool | None = None
    notas: TextoLargo | None = None
    motivo: Annotated[str, Field(max_length=1000)] | None = None


# --- Vínculos persona–unidad -----------------------------------------------------


class VinculoIn(_Base):
    """Vincula una persona existente (`persona_id`) o una nueva (`persona`)."""

    persona_id: uuid.UUID | None = None
    persona: PersonaIn | None = None
    relacion: RelacionUnidad
    porcentaje_propiedad: Porcentaje | None = None
    es_contacto_principal: bool | None = None  # None = automático (si la unidad no tiene)
    responsable_pago: bool | None = None  # None = automático (primer propietario)
    reside: bool = False
    fecha_inicio: date | None = None

    @model_validator(mode="after")
    def _una_persona(self) -> "VinculoIn":
        if (self.persona_id is None) == (self.persona is None):
            raise ValueError("Indique una persona existente o los datos de una nueva, no ambos")
        if self.porcentaje_propiedad is not None and self.relacion != RelacionUnidad.PROPIETARIO:
            raise ValueError("El porcentaje de propiedad solo aplica a propietarios")
        return self


class VinculoUpdate(_Base):
    porcentaje_propiedad: Porcentaje | None = None
    es_contacto_principal: bool | None = None
    responsable_pago: bool | None = None
    reside: bool | None = None


class CerrarVinculoIn(_Base):
    motivo: Annotated[str, Field(min_length=3, max_length=1000)]
    fecha_fin: date | None = None


# --- Vehículos ------------------------------------------------------------------


class _VehiculoCampos(_Base):
    @field_validator("placa", check_fields=False)
    @classmethod
    def _placa(cls, v: str | None) -> str | None:
        return None if v is None else d.normalizar_placa(v)


class VehiculoIn(_VehiculoCampos):
    placa: Annotated[str, Field(max_length=12)]
    tipo: TipoVehiculo = TipoVehiculo.CARRO
    marca: Annotated[str, Field(max_length=60)] | None = None
    color: Annotated[str, Field(max_length=40)] | None = None
    persona_id: uuid.UUID | None = None


class VehiculoUpdate(_VehiculoCampos):
    placa: Annotated[str, Field(max_length=12)] | None = None
    tipo: TipoVehiculo | None = None
    marca: Annotated[str, Field(max_length=60)] | None = None
    color: Annotated[str, Field(max_length=40)] | None = None
    persona_id: uuid.UUID | None = None
