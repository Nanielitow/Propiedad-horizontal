import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, UUIDPk
from app.models.enums import TaskStatus, pg_enum


class MinutesSummary(UUIDPk, CreatedAt, Base):
    __tablename__ = "minutes_summaries"

    tenant_id: Mapped[uuid.UUID]
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), unique=True)
    assembly_type: Mapped[str | None]
    assembly_date: Mapped[date | None]
    quorum_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    summary: Mapped[str | None]
    # [{topic, decision, approved, page, quote, verified}]
    agreements: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    # [{topic, yes_pct, no_pct, abstain_pct, result, page, quote, verified}]
    votes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    model: Mapped[str | None]


class ActionItem(UUIDPk, CreatedAt, Base):
    __tablename__ = "action_items"

    tenant_id: Mapped[uuid.UUID]
    minutes_summary_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("minutes_summaries.id"))
    description: Mapped[str]
    assignee: Mapped[str | None]
    due_date: Mapped[date | None]
    status: Mapped[TaskStatus] = mapped_column(pg_enum(TaskStatus, "task_status"), default=TaskStatus.OPEN)
    source_page: Mapped[int | None]
