"""Orquestación de la ingesta de un documento (se ejecuta en el worker de Celery).

descarga → verificación sha256 → extracción nativa → OCR (solo si hace falta)
→ chunking → embeddings → guardado atómico de páginas + chunks → READY

Cada etapa hace commit de `processing_jobs.current_step` para que el frontend
muestre el progreso. La re-ejecución es idempotente: borra páginas/chunks
previos del documento antes de insertar.
"""

import hashlib
import logging
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import delete, insert
from sqlalchemy.orm import Session

from app.db.rls import set_rls_context_sync
from app.db.session import SyncSessionLocal
from app.models import Document, DocumentChunk, DocumentPage, ProcessingJob
from app.models.enums import DocumentCategory, DocumentStatus, ExtractionMethod, JobStatus
from app.services.ingestion.chunker import Chunk, PageText, chunk_pages
from app.services.ingestion.errors import PermanentIngestionError
from app.services.ingestion.extract import ExtractedPage, extract_pages
from app.services.ingestion.ocr import ocr_pdf
from app.services.llm.embeddings import EmbeddingConfigError, get_embedder
from app.services.storage.s3 import get_storage

log = logging.getLogger(__name__)


def _system_session(tenant_id: uuid.UUID) -> Session:
    db = SyncSessionLocal()
    set_rls_context_sync(db, tenant_id=tenant_id, role="SYSTEM")
    return db


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _step(db: Session, job: ProcessingJob, name: str) -> None:
    job.current_step = name
    db.commit()
    log.info("ingesta job=%s paso=%s", job.id, name)


def _embedding_input(doc: Document, chunk: Chunk) -> str:
    # "Contextual chunk header": se embebe con título y sección para que un chunk
    # suelto ("La tarifa será de $50.000") conserve de qué documento viene.
    # En la base se guarda el contenido limpio, sin el encabezado.
    header = doc.title + (f" — {chunk.section_title}" if chunk.section_title else "")
    return f"{header}\n\n{chunk.content}"


def run_ingestion(job_id: uuid.UUID, tenant_id: uuid.UUID, document_id: uuid.UUID) -> DocumentCategory:
    storage = get_storage()
    with _system_session(tenant_id) as db:
        job = db.get(ProcessingJob, job_id)
        doc = db.get(Document, document_id)
        if job is None or doc is None or doc.deleted_at is not None:
            raise PermanentIngestionError("El documento o el job ya no existen")

        job.status = JobStatus.RUNNING
        job.attempts += 1
        job.started_at = job.started_at or datetime.now(UTC)
        job.error = None
        doc.status = DocumentStatus.PROCESSING
        _step(db, job, "download")

        try:
            embedder = get_embedder()
        except EmbeddingConfigError as exc:
            raise PermanentIngestionError(f"Configuración de embeddings: {exc}") from exc

        with TemporaryDirectory(prefix="ingest-") as tmp:
            src = Path(tmp) / "original.pdf"
            storage.download(doc.storage_key, src)
            if _sha256(src) != doc.sha256:
                raise PermanentIngestionError("El sha256 del archivo no coincide con el declarado")

            _step(db, job, "extract")
            pages = extract_pages(src)
            if not pages:
                raise PermanentIngestionError("El PDF no tiene páginas")

            ocr_pages = {p.page_number for p in pages if p.needs_ocr}
            if ocr_pages:
                _step(db, job, "ocr")
                ocr_path = Path(tmp) / "ocr.pdf"
                ocr_pdf(src, ocr_path)
                ocr_by_page = {p.page_number: p for p in extract_pages(ocr_path)}
                pages = [
                    replace(ocr_by_page[p.page_number], method=ExtractionMethod.OCR)
                    if p.page_number in ocr_pages and p.page_number in ocr_by_page
                    else p
                    for p in pages
                ]
                ocr_key = storage.document_key(tenant_id, document_id, "ocr.pdf")
                storage.upload(ocr_path, ocr_key)
                doc.ocr_storage_key = ocr_key

        _step(db, job, "chunking")
        chunks = chunk_pages([PageText(p.page_number, p.blocks) for p in pages])
        if not chunks:
            raise PermanentIngestionError("No se pudo extraer texto del documento (¿página en blanco?)")

        _step(db, job, "embedding")
        vectors = embedder.embed_documents([_embedding_input(doc, c) for c in chunks])

        # -- Guardado atómico: páginas + chunks + estado en UNA transacción ----------
        job.current_step = "saving"
        db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
        db.execute(delete(DocumentPage).where(DocumentPage.document_id == document_id))
        db.execute(insert(DocumentPage), [_page_row(tenant_id, document_id, p) for p in pages])
        db.execute(
            insert(DocumentChunk),
            [
                {
                    "id": uuid.uuid4(),
                    "tenant_id": tenant_id,
                    "document_id": document_id,
                    "chunk_index": c.index,
                    "page_number": c.page_number,
                    "page_end": c.page_end,
                    "category": doc.category,
                    "access_level": doc.access_level,
                    "section_title": c.section_title,
                    "content": c.content,
                    "token_count": c.token_count,
                    "embedding": vec,
                    "embedding_model": embedder.model,
                    "metadata_": {},
                }
                for c, vec in zip(chunks, vectors, strict=True)
            ],
        )

        now = datetime.now(UTC)
        doc.status = DocumentStatus.READY
        doc.page_count = len(pages)
        doc.is_scanned = bool(ocr_pages)
        doc.error_message = None
        doc.processed_at = now
        job.status = JobStatus.SUCCEEDED
        job.current_step = "done"
        job.finished_at = now
        job.result = {
            "pages": len(pages),
            "ocr_pages": sorted(ocr_pages),
            "chunks": len(chunks),
            "tokens": sum(c.token_count for c in chunks),
            "embedding_model": embedder.model,
        }
        db.commit()
        log.info("ingesta OK documento=%s %s", document_id, job.result)
        return doc.category


def _page_row(tenant_id: uuid.UUID, document_id: uuid.UUID, page: ExtractedPage) -> dict[str, object]:
    return {
        "id": uuid.uuid4(),
        "tenant_id": tenant_id,
        "document_id": document_id,
        "page_number": page.page_number,
        "text": page.text,
        "extraction_method": page.method,
    }


def mark_job(
    job_id: uuid.UUID,
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    *,
    status: JobStatus,
    error: str,
    fail_document: bool = True,
) -> None:
    """Registra un fallo/reintento con una sesión NUEVA (la anterior puede haber
    quedado en estado inválido tras la excepción). fail_document=False para jobs
    secundarios (p. ej. extracción de vencimientos): su fallo no invalida el
    documento, que sigue disponible en el buscador."""
    with _system_session(tenant_id) as db:
        job = db.get(ProcessingJob, job_id)
        doc = db.get(Document, document_id)
        if job:
            job.status = status
            job.error = error[:2000]
            if status == JobStatus.FAILED:
                job.finished_at = datetime.now(UTC)
        if doc and status == JobStatus.FAILED and fail_document:
            doc.status = DocumentStatus.FAILED
            doc.error_message = error[:500]
        db.commit()
