"""Activos, hojas de vida y plan de mantenimiento (migración 0005, docs/MANTENIMIENTO.md).

Columnas que asigna la base (consecutivos, códigos y costos generados, estados
iniciales por trigger) se leen tras el INSERT con FetchedValue + eager_defaults.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import FetchedValue, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPk
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
    pg_enum,
)

Money = Numeric(14, 2)
Textos = ARRAY(TEXT)
_DB = {"server_default": FetchedValue()}
_DB_ALWAYS = {"server_default": FetchedValue(), "server_onupdate": FetchedValue()}
_EAGER = {"eager_defaults": True}


class CategoriaActivo(UUIDPk, Base):
    __tablename__ = "categorias_activos"
    __mapper_args__ = _EAGER

    tenant_id: Mapped[uuid.UUID]
    codigo: Mapped[str]
    nombre: Mapped[str]
    descripcion: Mapped[str | None]
    subtipos: Mapped[list[str]] = mapped_column(Textos, default=list)
    es_infraestructura: Mapped[bool] = mapped_column(default=False)
    activo: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(**_DB)


class Contratista(UUIDPk, Base):
    __tablename__ = "contratistas"
    __mapper_args__ = _EAGER

    tenant_id: Mapped[uuid.UUID]
    razon_social: Mapped[str]
    nit: Mapped[str | None]
    contacto_nombre: Mapped[str | None]
    telefono: Mapped[str | None]
    email: Mapped[str | None]
    especialidades: Mapped[list[str]] = mapped_column(Textos, default=list)
    vigencia_contrato_inicio: Mapped[date | None]
    vigencia_contrato_fin: Mapped[date | None]
    alcance_contrato: Mapped[str | None]
    periodicidad_pactada: Mapped[str | None]
    valor_contrato: Mapped[Decimal | None] = mapped_column(Money)
    contrato_documento_id: Mapped[uuid.UUID | None]
    activo: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(**_DB)
    updated_at: Mapped[datetime] = mapped_column(**_DB_ALWAYS)


class Activo(UUIDPk, Base):
    __tablename__ = "activos"
    __mapper_args__ = _EAGER

    tenant_id: Mapped[uuid.UUID]
    consecutivo: Mapped[int] = mapped_column(**_DB)  # trigger: sin huecos por copropiedad
    codigo_interno: Mapped[str] = mapped_column(**_DB)  # generada: ACT-001
    qr_token: Mapped[str]
    nombre: Mapped[str]
    categoria_id: Mapped[uuid.UUID]
    subtipo: Mapped[str | None]
    ubicacion: Mapped[str]
    marca: Mapped[str | None]
    modelo: Mapped[str | None]
    fabricante: Mapped[str | None]
    numero_serie: Mapped[str | None]
    especificaciones: Mapped[dict[str, Any]] = mapped_column(default=dict)
    vida_util_anios: Mapped[int | None]
    fecha_instalacion: Mapped[date | None]
    instalador_id: Mapped[uuid.UUID | None]
    mantenedor_id: Mapped[uuid.UUID | None]
    fecha_vencimiento_garantia: Mapped[date | None]
    criticidad: Mapped[Criticidad] = mapped_column(pg_enum(Criticidad, "criticidad_activo"), default=Criticidad.MEDIA)
    estado: Mapped[EstadoActivo] = mapped_column(pg_enum(EstadoActivo, "estado_activo"), default=EstadoActivo.OPERATIVO)
    motivo_baja: Mapped[str | None]
    fecha_baja: Mapped[date | None]
    created_at: Mapped[datetime] = mapped_column(**_DB)
    updated_at: Mapped[datetime] = mapped_column(**_DB_ALWAYS)


class ActivoDocumento(Base):
    __tablename__ = "activo_documentos"

    activo_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    tipo: Mapped[TipoDocumentoActivo] = mapped_column(pg_enum(TipoDocumentoActivo, "tipo_documento_activo"))
    fecha_documento: Mapped[date | None]
    vinculado_por_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(**_DB)


class Evidencia(UUIDPk, Base):
    __tablename__ = "evidencias"
    __mapper_args__ = _EAGER

    tenant_id: Mapped[uuid.UUID]
    entidad: Mapped[EntidadEvidencia] = mapped_column(pg_enum(EntidadEvidencia, "entidad_evidencia"))
    entidad_id: Mapped[uuid.UUID]
    momento: Mapped[MomentoEvidencia] = mapped_column(pg_enum(MomentoEvidencia, "momento_evidencia"))
    storage_key: Mapped[str]
    content_type: Mapped[str]
    size_bytes: Mapped[int]
    descripcion: Mapped[str | None]
    subido_por_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(**_DB)


class LecturaUso(UUIDPk, Base):
    __tablename__ = "lecturas_uso"
    __mapper_args__ = _EAGER

    tenant_id: Mapped[uuid.UUID]
    activo_id: Mapped[uuid.UUID]
    fecha: Mapped[datetime] = mapped_column(**_DB)
    horas_acumuladas: Mapped[Decimal] = mapped_column(Numeric(10, 1))
    registrado_por_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class PlanPreventivo(UUIDPk, Base):
    __tablename__ = "planes_preventivos"
    __mapper_args__ = _EAGER

    tenant_id: Mapped[uuid.UUID]
    activo_id: Mapped[uuid.UUID]
    nombre: Mapped[str]
    actividades_checklist: Mapped[list[str]] = mapped_column(Textos, default=list)
    periodicidad: Mapped[Periodicidad] = mapped_column(pg_enum(Periodicidad, "periodicidad"))
    intervalo_horas: Mapped[int | None]
    base_calculo: Mapped[BaseCalculo] = mapped_column(
        pg_enum(BaseCalculo, "base_calculo_plan"), default=BaseCalculo.CALENDARIO_FIJO
    )
    fecha_inicio: Mapped[date]
    contratista_id: Mapped[uuid.UUID | None]
    costo_estimado: Mapped[Decimal | None] = mapped_column(Money)
    aprobado_por_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    aprobado_at: Mapped[datetime | None]
    activo: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(**_DB)
    updated_at: Mapped[datetime] = mapped_column(**_DB_ALWAYS)


class ActividadProgramada(UUIDPk, Base):
    __tablename__ = "actividades_programadas"
    __mapper_args__ = _EAGER

    tenant_id: Mapped[uuid.UUID]
    plan_id: Mapped[uuid.UUID]
    activo_id: Mapped[uuid.UUID]
    fecha_programada: Mapped[date]
    fecha_original: Mapped[date]
    estado: Mapped[EstadoActividad] = mapped_column(
        pg_enum(EstadoActividad, "estado_actividad"), default=EstadoActividad.PROGRAMADA
    )
    asignado_a_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(**_DB)
    updated_at: Mapped[datetime] = mapped_column(**_DB_ALWAYS)


class Reprogramacion(UUIDPk, Base):
    __tablename__ = "reprogramaciones"
    __mapper_args__ = _EAGER

    tenant_id: Mapped[uuid.UUID]
    actividad_id: Mapped[uuid.UUID]
    fecha_anterior: Mapped[date]
    nueva_fecha: Mapped[date]
    motivo: Mapped[str]
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(**_DB)


class Novedad(UUIDPk, Base):
    __tablename__ = "novedades"
    __mapper_args__ = _EAGER

    tenant_id: Mapped[uuid.UUID]
    consecutivo: Mapped[int] = mapped_column(**_DB)
    codigo: Mapped[str] = mapped_column(**_DB)  # generada: NOV-0001
    activo_id: Mapped[uuid.UUID]
    fecha_reporte: Mapped[datetime] = mapped_column(**_DB)
    reportado_por_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    descripcion: Mapped[str]
    riesgo_identificado: Mapped[str | None]
    prioridad: Mapped[PrioridadNovedad] = mapped_column(
        pg_enum(PrioridadNovedad, "prioridad_novedad"), default=PrioridadNovedad.MEDIA
    )
    # El estado inicial lo fija el trigger (siempre REPORTADA)
    estado: Mapped[EstadoNovedad] = mapped_column(pg_enum(EstadoNovedad, "estado_novedad"), **_DB)
    contratista_asignado_id: Mapped[uuid.UUID | None]
    asignado_a_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    cotizacion_id: Mapped[uuid.UUID | None]
    fecha_atencion: Mapped[datetime | None] = mapped_column(**_DB_ALWAYS)
    diagnostico: Mapped[str | None]
    solucion_implementada: Mapped[str | None]
    costo_reparacion: Mapped[Decimal | None] = mapped_column(Money)
    cerrada_por_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    cerrada_at: Mapped[datetime | None]
    motivo_descarte: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(**_DB)
    updated_at: Mapped[datetime] = mapped_column(**_DB_ALWAYS)


class MantenimientoEjecutado(UUIDPk, Base):
    __tablename__ = "mantenimientos_ejecutados"
    __mapper_args__ = _EAGER

    tenant_id: Mapped[uuid.UUID]
    consecutivo: Mapped[int] = mapped_column(**_DB)
    codigo: Mapped[str] = mapped_column(**_DB)  # generada: MTO-0001
    activo_id: Mapped[uuid.UUID]
    tipo: Mapped[TipoMantenimiento] = mapped_column(pg_enum(TipoMantenimiento, "tipo_mantenimiento"))
    fecha_ejecucion: Mapped[date]
    contratista_id: Mapped[uuid.UUID | None]
    nombre_tecnico: Mapped[str]
    tiempo_ejecucion_horas: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    diagnostico_inicial: Mapped[str | None]
    actividades_realizadas: Mapped[str]
    repuestos_utilizados: Mapped[str | None]
    novedades_encontradas: Mapped[str | None]
    recomendaciones_tecnico: Mapped[str | None]
    checklist: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    estado_post_intervencion: Mapped[EstadoActivo] = mapped_column(pg_enum(EstadoActivo, "estado_activo"))
    costo_mano_obra: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    costo_repuestos: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    costo_total: Mapped[Decimal] = mapped_column(Money, **_DB_ALWAYS)  # generada
    fecha_proximo_recomendado: Mapped[date | None]
    actividad_id: Mapped[uuid.UUID | None]
    novedad_id: Mapped[uuid.UUID | None]
    informe_documento_id: Mapped[uuid.UUID | None]
    factura_documento_id: Mapped[uuid.UUID | None]
    registrado_por_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    anulado_por_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    anulado_at: Mapped[datetime | None]
    motivo_anulacion: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(**_DB)


class RecomendacionTecnica(UUIDPk, Base):
    __tablename__ = "recomendaciones_tecnicas"
    __mapper_args__ = _EAGER

    tenant_id: Mapped[uuid.UUID]
    activo_id: Mapped[uuid.UUID]
    mantenimiento_origen_id: Mapped[uuid.UUID | None]
    descripcion: Mapped[str]
    prioridad: Mapped[PrioridadRecomendacion] = mapped_column(
        pg_enum(PrioridadRecomendacion, "prioridad_recomendacion"), default=PrioridadRecomendacion.MEDIA
    )
    responsable_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    fecha_limite: Mapped[date | None]
    costo_estimado: Mapped[Decimal | None] = mapped_column(Money)
    observaciones_administracion: Mapped[str | None]
    estado: Mapped[EstadoRecomendacion] = mapped_column(
        pg_enum(EstadoRecomendacion, "estado_recomendacion"), default=EstadoRecomendacion.PENDIENTE
    )
    justificacion_descarte: Mapped[str | None]
    mantenimiento_ejecucion_id: Mapped[uuid.UUID | None]
    creado_por_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(**_DB)
    updated_at: Mapped[datetime] = mapped_column(**_DB_ALWAYS)


class AuditoriaActivo(Base):
    """Solo lectura para la aplicación: la escribe un trigger de la base de datos."""

    __tablename__ = "auditoria_activos"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    entidad: Mapped[str]
    entidad_id: Mapped[uuid.UUID]
    activo_id: Mapped[uuid.UUID | None]
    usuario_id: Mapped[uuid.UUID | None]
    accion: Mapped[AccionAuditoria] = mapped_column(pg_enum(AccionAuditoria, "accion_auditoria"))
    valores_anteriores: Mapped[dict[str, Any] | None]
    valores_nuevos: Mapped[dict[str, Any] | None]
    motivo: Mapped[str | None]
    fecha_hora: Mapped[datetime]
