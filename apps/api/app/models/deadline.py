import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, func
from sqlalchemy.dialects.postgresql import ARRAY, INTEGER
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, UUIDPk
from app.models.enums import DeadlineStatus, DeadlineType, pg_enum

DEFAULT_REMINDER_DAYS = [30, 15, 7, 1]


class Deadline(UUIDPk, CreatedAt, Base):
    __tablename__ = "deadlines"

    tenant_id: Mapped[uuid.UUID]
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"))
    title: Mapped[str]
    type: Mapped[DeadlineType] = mapped_column(pg_enum(DeadlineType, "deadline_type"))
    status: Mapped[DeadlineStatus] = mapped_column(
        pg_enum(DeadlineStatus, "deadline_status"), default=DeadlineStatus.PENDING_REVIEW
    )
    due_date: Mapped[date]
    start_date: Mapped[date | None]
    recurrence_months: Mapped[int | None]
    provider_name: Mapped[str | None]
    source_page: Mapped[int | None]
    source_quote: Mapped[str | None]
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    reminder_days: Mapped[list[int]] = mapped_column(ARRAY(INTEGER), default=lambda: list(DEFAULT_REMINDER_DAYS))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None]
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


class DeadlineNotification(UUIDPk, Base):
    __tablename__ = "deadline_notifications"

    tenant_id: Mapped[uuid.UUID]
    deadline_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deadlines.id"))
    notify_on: Mapped[date]
    channel: Mapped[str] = mapped_column(default="in_app")
    sent_at: Mapped[datetime | None]
