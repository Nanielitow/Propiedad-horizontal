"""Esquemas de salida del módulo de unidades.

Los campos que un rol no puede ver llegan en `null` (no se omiten), para que el
frontend tenga una forma estable y simplemente no los muestre.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import (
    AccionAuditoria,
    OcupacionUnidad,
    RelacionUnidad,
    TipoDocumentoIdentidad,
    TipoUnidad,
    TipoVehiculo,
)


class UnidadRef(BaseModel):
    id: uuid.UUID
    etiqueta: str
    tipo: TipoUnidad


class PersonaRef(BaseModel):
    id: uuid.UUID
    nombre: str
    telefono: str | None = None


class PersonaOut(BaseModel):
    id: uuid.UUID
    nombre_completo: str
    telefono: str | None
    telefono_alterno: str | None
    tipo_documento: TipoDocumentoIdentidad | None  # null si el rol no puede verlo
    numero_documento: str | None
    email: str | None
    notas: str | None
    tiene_cuenta: bool
    autoriza_datos_at: datetime | None
    activa: bool


class VinculoOut(BaseModel):
    id: uuid.UUID
    unidad: UnidadRef
    persona: PersonaOut
    relacion: RelacionUnidad
    porcentaje_propiedad: Decimal | None
    es_contacto_principal: bool
    responsable_pago: bool
    reside: bool
    fecha_inicio: date
    fecha_fin: date | None
    motivo_cierre: str | None


class VehiculoOut(BaseModel):
    id: uuid.UUID
    unidad: UnidadRef
    persona: PersonaRef | None
    placa: str
    tipo: TipoVehiculo
    marca: str | None
    color: str | None
    activo: bool


class UnidadResumen(BaseModel):
    id: uuid.UUID
    etiqueta: str
    tower: str
    number: str
    tipo: TipoUnidad
    ocupacion: OcupacionUnidad
    activa: bool
    coefficient: Decimal | None  # null si el rol no ve datos prediales
    area_m2: Decimal | None
    unidad_principal: UnidadRef | None
    anexos: list[UnidadRef]
    propietarios: list[PersonaRef]
    contacto: PersonaRef | None
    responsable_pago: PersonaRef | None
    residentes: int
    vehiculos: int | None


class UnidadesPagina(BaseModel):
    items: list[UnidadResumen]
    total: int
    page: int
    page_size: int


class CoeficientesOut(BaseModel):
    suma: Decimal
    diferencia: Decimal
    cuadra: bool
    unidades_con_coeficiente: int
    unidades_sin_coeficiente: int
    mensaje: str


class ResumenUnidades(BaseModel):
    total: int
    por_tipo: dict[str, int]
    por_ocupacion: dict[str, int]
    sin_propietario: int
    sin_responsable_pago: int
    personas: int | None
    vehiculos: int | None
    torres: list[str]
    coeficientes: CoeficientesOut | None


class AuditoriaOut(BaseModel):
    fecha_hora: datetime
    entidad: str
    accion: AccionAuditoria
    usuario: str | None
    motivo: str | None
    cambios: dict[str, object] | None


class RecaudoUnidad(BaseModel):
    id: uuid.UUID
    consecutivo: int
    fecha_recaudo: datetime
    concepto: str
    valor: Decimal
    estado: str


class UnidadDetalle(UnidadResumen):
    matricula_inmobiliaria: str | None
    observaciones: str | None
    ocupacion_sugerida: OcupacionUnidad
    vinculos: list[VinculoOut]
    historial: list[VinculoOut]  # vínculos cerrados (solo personal administrativo)
    vehiculos_lista: list[VehiculoOut]
    recaudos: list[RecaudoUnidad]
    auditoria: list[AuditoriaOut]
    created_at: datetime
    updated_at: datetime


class PersonaResumen(PersonaOut):
    unidades: list[UnidadRef]
    relaciones: list[RelacionUnidad]


class PersonasPagina(BaseModel):
    items: list[PersonaResumen]
    total: int
    page: int
    page_size: int


class PersonaDetalle(PersonaOut):
    vinculos: list[VinculoOut]
    vehiculos: list[VehiculoOut]


class PlacaOut(BaseModel):
    placa: str
    registrada: bool
    vehiculo: VehiculoOut | None
