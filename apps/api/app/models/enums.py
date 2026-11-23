"""Espejo de los tipos ENUM de PostgreSQL (definidos en la migración 0001)."""

from enum import StrEnum

from sqlalchemy.dialects.postgresql import ENUM


class UserRole(StrEnum):
    ADMIN = "ADMIN"
    RESIDENTE = "RESIDENTE"
    # Módulo de recaudos (migración 0003)
    AUXILIAR = "AUXILIAR"  # recepción: registra recaudos y cierra su caja
    CONTABILIDAD = "CONTABILIDAD"  # verifica y concilia; no registra
    CONSEJO = "CONSEJO"  # solo lectura de dashboard y cortes mensuales


class AccessLevel(StrEnum):
    ADMIN = "ADMIN"
    PUBLIC = "PUBLIC"


class DocumentCategory(StrEnum):
    MANTENIMIENTO = "MANTENIMIENTO"
    ACTAS = "ACTAS"
    CONTRATOS = "CONTRATOS"
    FINANCIERO = "FINANCIERO"
    CONVIVENCIA = "CONVIVENCIA"
    COMUNICADOS = "COMUNICADOS"
    COTIZACIONES = "COTIZACIONES"


# Categorías visibles para residentes por defecto (el admin puede sobrescribir)
PUBLIC_BY_DEFAULT = {DocumentCategory.CONVIVENCIA, DocumentCategory.COMUNICADOS}


class DocumentStatus(StrEnum):
    UPLOADED = "UPLOADED"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"


class ExtractionMethod(StrEnum):
    NATIVE = "NATIVE"
    OCR = "OCR"


class JobType(StrEnum):
    INGEST = "INGEST"
    EXTRACT_DEADLINES = "EXTRACT_DEADLINES"
    SUMMARIZE_MINUTES = "SUMMARIZE_MINUTES"
    COMPARE_QUOTES = "COMPARE_QUOTES"


class JobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"


class DeadlineType(StrEnum):
    POLICY_EXPIRY = "POLICY_EXPIRY"  # vencimiento de póliza de seguro
    CONTRACT_END = "CONTRACT_END"  # terminación / renovación de contrato
    MAINTENANCE = "MAINTENANCE"  # próximo mantenimiento (ascensores, tanques...)
    CERTIFICATION = "CERTIFICATION"  # certificados, inspecciones, permisos
    OTHER = "OTHER"


class DeadlineStatus(StrEnum):
    PENDING_REVIEW = "PENDING_REVIEW"  # detectado por IA, sin confirmar
    ACTIVE = "ACTIVE"  # confirmado por un admin: genera alertas
    DONE = "DONE"  # renovado / realizado
    DISMISSED = "DISMISSED"  # descartado (falso positivo)


# Categorías en las que se buscan fechas de vencimiento al procesar un documento
DEADLINE_CATEGORIES = {DocumentCategory.CONTRATOS, DocumentCategory.MANTENIMIENTO, DocumentCategory.ACTAS}


class TaskStatus(StrEnum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


# --- Recaudos (migración 0003) ---------------------------------------------


class TipoCobro(StrEnum):
    FIJO = "FIJO"
    POR_HORA = "POR_HORA"
    VARIABLE = "VARIABLE"


class MedioPago(StrEnum):
    EFECTIVO = "EFECTIVO"
    TRANSFERENCIA = "TRANSFERENCIA"
    CONSIGNACION = "CONSIGNACION"


class EstadoRecaudo(StrEnum):
    RECAUDADO_EN_CAJA = "RECAUDADO_EN_CAJA"  # efectivo en poder de recepción
    ENTREGADO_ADMINISTRACION = "ENTREGADO_ADMINISTRACION"  # trasladado a administración/tesorería
    PENDIENTE_VERIFICACION = "PENDIENTE_VERIFICACION"  # transferencia sin validar en el extracto
    CONSIGNADO = "CONSIGNADO"  # efectivo ya depositado en el banco
    VERIFICADO = "VERIFICADO"  # conciliado por contabilidad
    ANULADO = "ANULADO"  # borrado lógico con motivo


class EstadoReserva(StrEnum):
    SOLICITADA = "SOLICITADA"
    CONFIRMADA = "CONFIRMADA"
    CANCELADA = "CANCELADA"
    REALIZADA = "REALIZADA"


class EstadoEntrega(StrEnum):
    PENDIENTE_CONFIRMACION = "PENDIENTE_CONFIRMACION"
    CONFIRMADA = "CONFIRMADA"
    RECHAZADA = "RECHAZADA"


class EstadoConsignacion(StrEnum):
    REGISTRADA = "REGISTRADA"
    APROBADA = "APROBADA"
    VERIFICADA = "VERIFICADA"
    RECHAZADA = "RECHAZADA"


class AccionAuditoria(StrEnum):
    CREACION = "CREACION"
    EDICION = "EDICION"
    CAMBIO_ESTADO = "CAMBIO_ESTADO"
    ANULACION = "ANULACION"


class TipoAlerta(StrEnum):
    DIFERENCIA_CIERRE = "DIFERENCIA_CIERRE"
    DESCUADRE_CONSIGNACION = "DESCUADRE_CONSIGNACION"
    DESCUADRE_ENTREGA = "DESCUADRE_ENTREGA"
    TRANSFERENCIA_SIN_VERIFICAR = "TRANSFERENCIA_SIN_VERIFICAR"
    ANULACION_POSTERIOR = "ANULACION_POSTERIOR"


class SeveridadAlerta(StrEnum):
    INFO = "INFO"
    ADVERTENCIA = "ADVERTENCIA"
    CRITICA = "CRITICA"


class EstadoAlerta(StrEnum):
    ABIERTA = "ABIERTA"
    ATENDIDA = "ATENDIDA"


def pg_enum(enum_cls: type[StrEnum], name: str) -> ENUM:
    # values_callable: SQLAlchemy guarda por defecto el NOMBRE del miembro (USER);
    # el ENUM de Postgres usa el VALOR ('user').
    return ENUM(
        enum_cls,
        name=name,
        create_type=False,
        values_callable=lambda e: [m.value for m in e],
    )
