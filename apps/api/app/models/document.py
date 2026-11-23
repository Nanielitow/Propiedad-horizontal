import uuid
from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Computed, ForeignKey, Identity, func, text
from sqlalchemy.dialects.postgresql import INET, TSVECTOR
from sqlalchemy.orm import Mapped, deferred, mapped_column

from app.models.base import Base, CreatedAt, UUIDPk
from app.models.enums import (
    AccessLevel,
    DocumentCategory,
    DocumentStatus,
    ExtractionMethod,
    JobStatus,
    JobType,
    pg_enum,
)

EMBEDDING_DIM = 1536  # debe coincidir con vector(1536) en la migración 0001


class Document(UUIDPk, CreatedAt, Base):
    __tablename__ = "documents"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str]
    original_filename: Mapped[str]
    category: Mapped[DocumentCategory] = mapped_column(pg_enum(DocumentCategory, "document_category"))
    access_level: Mapped[AccessLevel] = mapped_column(pg_enum(AccessLevel, "access_level"))
    status: Mapped[DocumentStatus] = mapped_column(
        pg_enum(DocumentStatus, "document_status"), default=DocumentStatus.UPLOADED
    )
    storage_key: Mapped[str]
    ocr_storage_key: Mapped[str | None]
    mime_type: Mapped[str] = mapped_column(default="application/pdf")
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str]
    page_count: Mapped[int | None]
    is_scanned: Mapped[bool | None]
    document_date: Mapped[date | None]
    error_message: Mapped[str | None]
    processed_at: Mapped[datetime | None]
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())
    deleted_at: Mapped[datetime | None]
    # Origen (migración 0004): UPLOAD o GOOGLE_DRIVE, con el id y el enlace del original
    source: Mapped[str] = mapped_column(default="UPLOAD")
    source_ref: Mapped[str | None]
    source_url: Mapped[str | None]


class DocumentPage(UUIDPk, Base):
    __tablename__ = "document_pages"

    tenant_id: Mapped[uuid.UUID]
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"))
    page_number: Mapped[int]
    text: Mapped[str]
    extraction_method: Mapped[ExtractionMethod] = mapped_column(pg_enum(ExtractionMethod, "extraction_method"))
    ocr_confidence: Mapped[float | None]


class DocumentChunk(UUIDPk, CreatedAt, Base):
    __tablename__ = "document_chunks"

    tenant_id: Mapped[uuid.UUID]
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"))
    chunk_index: Mapped[int]
    page_number: Mapped[int]
    page_end: Mapped[int]
    category: Mapped[DocumentCategory] = mapped_column(pg_enum(DocumentCategory, "document_category"))
    access_level: Mapped[AccessLevel] = mapped_column(pg_enum(AccessLevel, "access_level"))
    section_title: Mapped[str | None]
    content: Mapped[str]
    token_count: Mapped[int]
    # Columna generada por Postgres: nunca se escribe, y no se carga por defecto
    content_tsv: Mapped[Any] = deferred(
        mapped_column(TSVECTOR, Computed("to_tsvector('es_unaccent', content)", persisted=True))
    )
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    embedding_model: Mapped[str]
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", server_default=text("'{}'::jsonb"))


class ProcessingJob(UUIDPk, CreatedAt, Base):
    __tablename__ = "processing_jobs"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id"))
    type: Mapped[JobType] = mapped_column(pg_enum(JobType, "job_type"))
    status: Mapped[JobStatus] = mapped_column(pg_enum(JobStatus, "job_status"), default=JobStatus.PENDING)
    celery_task_id: Mapped[str | None]
    attempts: Mapped[int] = mapped_column(default=0)
    current_step: Mapped[str | None]
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    result: Mapped[dict[str, Any] | None]
    error: Mapped[str | None]
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str]
    entity_type: Mapped[str | None]
    entity_id: Mapped[uuid.UUID | None]
    ip: Mapped[str | None] = mapped_column(INET)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
