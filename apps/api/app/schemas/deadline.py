import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from app.models.enums import DeadlineStatus, DeadlineType


class DeadlineOut(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    title: str
    type: DeadlineType
    status: DeadlineStatus
    due_date: date
    start_date: date | None
    recurrence_months: int | None
    provider_name: str | None
    source_page: int | None
    source_quote: str | None
    confidence: float | None
    reminder_days: list[int]
    reviewed_at: datetime | None
    created_at: datetime


class AnalyzingDocument(BaseModel):
    document_id: uuid.UUID
    title: str
    status: str


class DeadlinesResponse(BaseModel):
    deadlines: list[DeadlineOut]
    # Documentos que el detector está analizando ahora (el frontend muestra un aviso y consulta de nuevo)
    analyzing: list[AnalyzingDocument]


class DeadlineUpdate(BaseModel):
    """Todos los campos son opcionales; solo se modifican los que se envían."""

    title: str | None = Field(default=None, min_length=2, max_length=200)
    type: DeadlineType | None = None
    due_date: date | None = None
    provider_name: str | None = Field(default=None, max_length=200)
    recurrence_months: int | None = Field(default=None, ge=1, le=120)
    reminder_days: list[int] | None = None
    status: DeadlineStatus | None = None

    @field_validator("reminder_days")
    @classmethod
    def _valid_reminders(cls, v: list[int] | None) -> list[int] | None:
        if v is None:
            return v
        if any(d < 0 or d > 365 for d in v):
            raise ValueError("Los recordatorios deben estar entre 0 y 365 días")
        return sorted(set(v), reverse=True)

    @field_validator("status")
    @classmethod
    def _no_done_here(cls, v: DeadlineStatus | None) -> DeadlineStatus | None:
        if v == DeadlineStatus.DONE:
            raise ValueError("Para marcar como realizado use POST /{id}/complete")
        return v


class CompleteResponse(BaseModel):
    completed: DeadlineOut
    next: DeadlineOut | None


class ScanRequest(BaseModel):
    document_id: uuid.UUID
