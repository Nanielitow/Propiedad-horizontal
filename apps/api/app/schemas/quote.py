import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models.enums import JobStatus


class ComparisonCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    document_ids: list[uuid.UUID] = Field(min_length=2, max_length=4)

    @field_validator("document_ids")
    @classmethod
    def _unique(cls, v: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(set(v)) != len(v):
            raise ValueError("Hay cotizaciones repetidas")
        return v


class ComparisonDocumentOut(BaseModel):
    document_id: uuid.UUID
    document_title: str
    provider_name: str | None
    extracted: dict[str, Any] | None


class ComparisonSummary(BaseModel):
    id: uuid.UUID
    title: str
    status: JobStatus
    created_at: datetime
    providers: list[str]
    min_total: float | None
    progress: str | None


class ComparisonOut(BaseModel):
    id: uuid.UUID
    title: str
    status: JobStatus
    created_at: datetime
    model: str | None
    progress: str | None
    error: str | None
    best: dict[str, Any] | None
    analysis: dict[str, Any] | None
    documents: list[ComparisonDocumentOut]
