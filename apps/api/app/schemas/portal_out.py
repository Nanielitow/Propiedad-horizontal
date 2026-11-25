"""Esquemas de salida del portal del residente."""

import uuid
from datetime import date, datetime, time
from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import (
    CanalPqrs,
    CategoriaCircular,
    CategoriaPqrs,
    EstadoCircular,
    EstadoPqrs,
    EstadoReserva,
    PrioridadPqrs,
    TipoPqrs,
)


class AdjuntoOut(BaseModel):
    nombre: str
    tipo: str
    tamano: int | None = None
    url: str


class PqrsResumen(BaseModel):
    id: uuid.UUID
    radicado: str
    tipo: TipoPqrs
    categoria: CategoriaPqrs
    asunto: str
    estado: EstadoPqrs
    prioridad: PrioridadPqrs
    canal: CanalPqrs
    unidad: str | None
    solicitante_nombre: str
    asignado_a: str | None
    fecha_limite: date
    dias_habiles_restantes: int | None  # None si ya no está abierta
    vencida: bool
    calificacion: int | None
    mensajes: int
    created_at: datetime
    updated_at: datetime


class MensajeOut(BaseModel):
    id: uuid.UUID
    autor: str
    autor_rol: str
    es_mio: bool
    texto: str
    interno: bool
    es_respuesta: bool
    adjuntos: list[AdjuntoOut]
    created_at: datetime


class PqrsDetalle(PqrsResumen):
    descripcion: str
    solicitante_contacto: str | None
    adjuntos: list[AdjuntoOut]
    comentario_calificacion: str | None
    respondida_at: datetime | None
    cerrada_at: datetime | None
    novedad_id: uuid.UUID | None
    novedad_codigo: str | None
    hilo: list[MensajeOut]
    es_mia: bool
    puede_gestionar: bool


class PqrsResumenBandeja(BaseModel):
    por_estado: dict[str, int]
    abiertas: int
    vencidas: int
    por_vencer: int  # 3 días hábiles o menos
    sin_asignar: int
    tiempo_respuesta_promedio_dias: Decimal | None
    satisfaccion_promedio: Decimal | None


class CircularOut(BaseModel):
    id: uuid.UUID
    numero: str | None
    titulo: str
    cuerpo: str
    categoria: CategoriaCircular
    importante: bool
    torres: list[str]
    estado: EstadoCircular
    document_id: uuid.UUID | None
    documento_titulo: str | None
    enviar_correo: bool
    publicada_at: datetime | None
    vigente_hasta: date | None
    leida: bool
    lecturas: int | None  # solo personal
    destinatarios_con_cuenta: int | None
    correos_enviados: int
    created_at: datetime


class ZonaOut(BaseModel):
    id: uuid.UUID
    nombre: str
    descripcion: str | None
    capacidad: int | None
    reglas: str | None
    tarifa_alquiler: Decimal | None
    tarifa_aseo: Decimal | None
    hora_apertura: time
    hora_cierre: time
    anticipacion_min_dias: int
    anticipacion_max_dias: int
    max_reservas_mes_unidad: int
    requiere_paz_y_salvo: bool
    requiere_aprobacion: bool
    reservable_residentes: bool
    activo: bool


class OcupadoOut(BaseModel):
    fecha_evento: date
    hora_inicio: time | None
    hora_fin: time | None
    propia: bool


class ReservaOut(BaseModel):
    id: uuid.UUID
    zona_id: uuid.UUID
    zona: str
    unidad_id: uuid.UUID | None
    unidad: str | None
    solicitante: str
    fecha_evento: date
    hora_inicio: time | None
    hora_fin: time | None
    numero_asistentes: int | None
    estado: EstadoReserva
    observaciones: str | None
    solicitada_en_portal: bool
    motivo_decision: str | None
    decidida_at: datetime | None
    tarifa_total: Decimal | None
    created_at: datetime


class InicioResidente(BaseModel):
    nombre: str
    unidades: list[str]
    saldo_total: Decimal | None
    saldo_vencido: Decimal | None
    al_dia: bool | None
    proximas_reservas: list[ReservaOut]
    pqrs_abiertas: list[PqrsResumen]
    pqrs_por_calificar: int
    circulares_sin_leer: list[CircularOut]
    zonas_reservables: int


class PendientesPersonal(BaseModel):
    pqrs_abiertas: int
    pqrs_vencidas: int
    pqrs_sin_asignar: int
    reservas_por_decidir: int
    circulares_borrador: int
