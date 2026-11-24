"""Respuestas de la API de activos y mantenimiento.

Los campos de costo llegan en null para los roles que no los ven (auxiliar y
técnico de mantenimiento, docs/MANTENIMIENTO.md §3): lo decide la capa de
consultas, no el frontend.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.models.enums import (
    AccionAuditoria,
    BaseCalculo,
    Criticidad,
    EntidadEvidencia,
    EstadoActividad,
    EstadoActivo,
    EstadoNovedad,
    EstadoRecomendacion,
    MomentoEvidencia,
    Periodicidad,
    PrioridadNovedad,
    PrioridadRecomendacion,
    TipoDocumentoActivo,
    TipoMantenimiento,
)

Color = Literal["VERDE", "AMARILLO", "ROJO"]


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Ref(BaseModel):
    """Referencia corta a otro registro para mostrar su nombre sin otra consulta."""

    id: uuid.UUID
    nombre: str


# --- Catálogos ---------------------------------------------------------------------------


class CategoriaOut(_Out):
    id: uuid.UUID
    codigo: str
    nombre: str
    descripcion: str | None
    subtipos: list[str]
    es_infraestructura: bool


class ContratistaOut(_Out):
    id: uuid.UUID
    razon_social: str
    nit: str | None
    contacto_nombre: str | None
    telefono: str | None
    email: str | None
    especialidades: list[str]
    vigencia_contrato_inicio: date | None
    vigencia_contrato_fin: date | None
    alcance_contrato: str | None
    periodicidad_pactada: str | None
    valor_contrato: Decimal | None
    contrato_documento_id: uuid.UUID | None
    activo: bool


class ContratistaDetalle(ContratistaOut):
    activos: list[Ref]
    mantenimientos: int
    correctivos: int
    costo_total: Decimal | None


class PersonaOut(BaseModel):
    id: uuid.UUID
    nombre: str
    rol: str


# --- Activos -------------------------------------------------------------------------------


class ActivoResumen(_Out):
    id: uuid.UUID
    codigo_interno: str
    nombre: str
    categoria: Ref
    subtipo: str | None
    ubicacion: str
    estado: EstadoActivo
    criticidad: Criticidad
    semaforo: Color | None
    proxima_fecha: date | None
    novedades_abiertas: int


class ActivosPagina(BaseModel):
    items: list[ActivoResumen]
    total: int
    page: int
    page_size: int
    por_semaforo: dict[str, int]
    por_estado: dict[str, int]


class DocumentoVinculado(BaseModel):
    document_id: uuid.UUID
    titulo: str
    tipo: TipoDocumentoActivo
    fecha_documento: date | None
    vinculado_at: datetime


class VencimientoOut(_Out):
    id: uuid.UUID
    title: str
    due_date: date | None
    status: str


class LecturaOut(_Out):
    id: uuid.UUID
    fecha: datetime
    horas_acumuladas: Decimal


class EstadoHorasOut(BaseModel):
    plan_id: uuid.UUID
    intervalo_horas: int
    horas_desde_ultimo: Decimal
    horas_restantes: Decimal
    uso_diario: Decimal | None
    fecha_estimada: date | None


class ActividadOut(BaseModel):
    id: uuid.UUID
    plan: Ref
    activo: Ref
    activo_codigo: str
    ubicacion: str
    fecha_programada: date
    fecha_original: date
    estado: EstadoActividad
    asignado_a: Ref | None
    contratista: Ref | None
    semaforo: Color | None
    dias_restantes: int | None
    reprogramada: bool
    mantenimiento_id: uuid.UUID | None


class PlanOut(BaseModel):
    id: uuid.UUID
    activo: Ref
    activo_codigo: str
    nombre: str
    actividades_checklist: list[str]
    periodicidad: Periodicidad
    intervalo_horas: int | None
    base_calculo: BaseCalculo
    fecha_inicio: date
    contratista: Ref | None
    costo_estimado: Decimal | None
    aprobado: bool
    aprobado_por: Ref | None
    aprobado_at: datetime | None
    activo_plan: bool
    proxima_fecha: date | None
    ejecuciones: int


class MantenimientoResumen(BaseModel):
    id: uuid.UUID
    codigo: str
    activo: Ref
    activo_codigo: str
    tipo: TipoMantenimiento
    fecha_ejecucion: date
    nombre_tecnico: str
    contratista: Ref | None
    estado_post_intervencion: EstadoActivo
    costo_total: Decimal | None
    anulado: bool


class MantenimientoDetalle(MantenimientoResumen):
    tiempo_ejecucion_horas: Decimal | None
    diagnostico_inicial: str | None
    actividades_realizadas: str
    repuestos_utilizados: str | None
    novedades_encontradas: str | None
    recomendaciones_tecnico: str | None
    checklist: list[dict[str, Any]]
    costo_mano_obra: Decimal | None
    costo_repuestos: Decimal | None
    fecha_proximo_recomendado: date | None
    actividad_id: uuid.UUID | None
    plan: Ref | None
    novedad: Ref | None
    informe_documento_id: uuid.UUID | None
    factura_documento_id: uuid.UUID | None
    registrado_por: Ref
    created_at: datetime
    anulado_por: Ref | None
    anulado_at: datetime | None
    motivo_anulacion: str | None
    recomendaciones: list["RecomendacionOut"]


class NovedadOut(BaseModel):
    id: uuid.UUID
    codigo: str
    activo: Ref
    activo_codigo: str
    ubicacion: str
    fecha_reporte: datetime
    reportado_por: Ref
    descripcion: str
    riesgo_identificado: str | None
    prioridad: PrioridadNovedad
    estado: EstadoNovedad
    contratista_asignado: Ref | None
    asignado_a: Ref | None
    cotizacion_id: uuid.UUID | None
    fecha_atencion: datetime | None
    diagnostico: str | None
    solucion_implementada: str | None
    costo_reparacion: Decimal | None
    cerrada_por: Ref | None
    cerrada_at: datetime | None
    motivo_descarte: str | None
    mantenimientos: list[Ref]
    horas_sin_atender: int | None


class RecomendacionOut(BaseModel):
    id: uuid.UUID
    activo: Ref
    activo_codigo: str
    mantenimiento_origen: Ref | None
    descripcion: str
    prioridad: PrioridadRecomendacion
    estado: EstadoRecomendacion
    responsable: Ref | None
    fecha_limite: date | None
    vencida: bool
    costo_estimado: Decimal | None
    observaciones_administracion: str | None
    justificacion_descarte: str | None
    mantenimiento_ejecucion_id: uuid.UUID | None
    created_at: datetime


class EvidenciaOut(BaseModel):
    id: uuid.UUID
    entidad: EntidadEvidencia
    entidad_id: uuid.UUID
    momento: MomentoEvidencia
    content_type: str
    size_bytes: int
    descripcion: str | None
    subido_por: Ref | None
    created_at: datetime
    url: str


class EvidenciaUploadOut(BaseModel):
    storage_key: str
    upload_url: str
    headers: dict[str, str]
    expires_in: int


class ActivoDetalle(BaseModel):
    """Hoja de vida completa: ficha técnica, estado, plan, historial, novedades y costos."""

    id: uuid.UUID
    codigo_interno: str
    qr_token: str
    qr_url: str
    nombre: str
    categoria: Ref
    subtipo: str | None
    ubicacion: str
    marca: str | None
    modelo: str | None
    fabricante: str | None
    numero_serie: str | None
    especificaciones: dict[str, Any]
    vida_util_anios: int | None
    vida_util_consumida: Decimal | None
    fecha_instalacion: date | None
    instalador: Ref | None
    mantenedor: Ref | None
    fecha_vencimiento_garantia: date | None
    garantia_vigente: bool | None
    criticidad: Criticidad
    estado: EstadoActivo
    motivo_baja: str | None
    fecha_baja: date | None
    semaforo: Color | None
    created_at: datetime
    updated_at: datetime
    documentos: list[DocumentoVinculado]
    vencimientos: list[VencimientoOut]
    planes: list[PlanOut]
    proximas_actividades: list[ActividadOut]
    mantenimientos: list[MantenimientoResumen]
    novedades: list[NovedadOut]
    recomendaciones: list[RecomendacionOut]
    lecturas: list[LecturaOut]
    horas: list[EstadoHorasOut]
    costo_acumulado: Decimal | None
    costo_anio: Decimal | None
    puede_ver_costos: bool


class QrResuelto(BaseModel):
    """Vista rápida desde el QR: lo justo para actuar en sitio."""

    id: uuid.UUID
    codigo_interno: str
    nombre: str
    ubicacion: str
    estado: EstadoActivo
    criticidad: Criticidad
    semaforo: Color | None
    ultimo_mantenimiento: MantenimientoResumen | None
    proxima_actividad: ActividadOut | None
    novedades_abiertas: list[NovedadOut]
    usa_horometro: bool


class AuditoriaOut(BaseModel):
    id: int
    entidad: str
    entidad_id: uuid.UUID
    accion: AccionAuditoria
    usuario: Ref | None
    valores_anteriores: dict[str, Any] | None
    valores_nuevos: dict[str, Any] | None
    motivo: str | None
    fecha_hora: datetime


class ReprogramacionOut(_Out):
    id: uuid.UUID
    fecha_anterior: date
    nueva_fecha: date
    motivo: str
    created_at: datetime


MantenimientoDetalle.model_rebuild()
