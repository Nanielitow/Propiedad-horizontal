import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AccessLevel, DocumentCategory, DocumentStatus, JobStatus


class UploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$", description="Hash calculado en el navegador")
    category: DocumentCategory
    title: str | None = Field(default=None, max_length=255)
    access_level: AccessLevel | None = Field(
        default=None, description="Si se omite: PUBLIC para Convivencia/Comunicados, ADMIN para el resto"
    )


class UploadResponse(BaseModel):
    document_id: uuid.UUID
    upload_url: str
    method: str = "PUT"
    headers: dict[str, str]
    expires_in: int


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: JobStatus
    current_step: str | None
    attempts: int
    error: str | None
    result: dict[str, Any] | None


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    original_filename: str
    category: DocumentCategory
    access_level: AccessLevel
    status: DocumentStatus
    size_bytes: int
    page_count: int | None
    is_scanned: bool | None
    error_message: str | None
    created_at: datetime
    processed_at: datetime | None
    source: str = "UPLOAD"
    source_url: str | None = None
    job: JobOut | None = None


class FileUrlResponse(BaseModel):
    url: str
    expires_in: int
    is_ocr_version: bool


# --- Importación desde Google Drive -------------------------------------------------


class DriveFileRef(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{10,200}$")


class DriveImportRequest(BaseModel):
    # Token de acceso de Google (alcance drive.file) obtenido en el navegador: se usa
    # en esta misma petición para descargar y se descarta; nunca se guarda.
    access_token: str = Field(min_length=20, max_length=4096, repr=False)
    files: list[DriveFileRef] = Field(min_length=1, max_length=20)
    category: DocumentCategory
    access_level: AccessLevel | None = None


class DriveImportResult(BaseModel):
    file_id: str
    nombre: str | None
    estado: Literal["IMPORTADO", "DUPLICADO", "ERROR"]
    document_id: uuid.UUID | None = None
    mensaje: str | None = None


class DriveImportResponse(BaseModel):
    resultados: list[DriveImportResult]
