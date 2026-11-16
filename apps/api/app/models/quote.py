import uuid
from typing import Any

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, UUIDPk
from app.models.enums import JobStatus, pg_enum


class QuoteComparison(UUIDPk, CreatedAt, Base):
    __tablename__ = "quote_comparisons"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str]
    status: Mapped[JobStatus] = mapped_column(pg_enum(JobStatus, "job_status"), default=JobStatus.PENDING)
    # {"progress": ..., "best": {...}, "analysis": {...}, "error": ...}
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    recommendation: Mapped[str | None]
    model: Mapped[str | None]


class QuoteComparisonDocument(Base):
    __tablename__ = "quote_comparison_documents"

    tenant_id: Mapped[uuid.UUID]
    comparison_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("quote_comparisons.id"), primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), primary_key=True)
    provider_name: Mapped[str | None]
    extracted: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
