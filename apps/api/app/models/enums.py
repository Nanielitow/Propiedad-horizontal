"""Espejo de los tipos ENUM de PostgreSQL (definidos en la migración 0001)."""

from enum import StrEnum

from sqlalchemy.dialects.postgresql import ENUM


class UserRole(StrEnum):
    ADMIN = "ADMIN"
    RESIDENTE = "RESIDENTE"


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


def pg_enum(enum_cls: type[StrEnum], name: str) -> ENUM:
    # values_callable: SQLAlchemy guarda por defecto el NOMBRE del miembro (USER);
    # el ENUM de Postgres usa el VALOR ('user').
    return ENUM(
        enum_cls,
        name=name,
        create_type=False,
        values_callable=lambda e: [m.value for m in e],
    )
