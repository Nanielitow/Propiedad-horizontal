import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import DocumentCategory, MessageRole


class SearchHit(BaseModel):
    n: int
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    page_number: int
    page_end: int
    category: str
    section_title: str | None
    snippet: str
    score: float
    semantic_distance: float | None


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    conversation_id: uuid.UUID | None = None
    categories: list[DocumentCategory] | None = None


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str | None
    created_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: MessageRole
    content: str
    citations: list[dict[str, Any]]
    created_at: datetime
