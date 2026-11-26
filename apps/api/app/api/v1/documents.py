"""Documentos: subida directa a S3 con URL firmada + ingesta asíncrona.

Flujo de subida (3 pasos, el archivo nunca pasa por la API):
  1. POST /uploads              -> crea el registro (UPLOADED) y devuelve URL PUT firmada
  2. PUT <upload_url>           -> el navegador sube el PDF directo a S3/R2
  3. POST /{id}/complete        -> la API verifica el objeto y encola la ingesta (QUEUED)
"""

import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import PurePath

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminCtx, DbSession, TenantContext, TenantCtx
from app.core.config import get_settings
from app.core.rate_limit import DEMO_UPLOADS_PER_IP_DAY, UPLOADS_PER_HOUR, enforce, enforce_demo
from app.models import Document, ProcessingJob
from app.models.enums import (
    PUBLIC_BY_DEFAULT,
    AccessLevel,
    DocumentCategory,
    DocumentStatus,
    JobStatus,
    JobType,
)
from app.schemas.document import (
    DocumentOut,
    DriveImportRequest,
    DriveImportResponse,
    DriveImportResult,
    FileUrlResponse,
    JobOut,
    UploadRequest,
    UploadResponse,
)
from app.services import google_drive
from app.services.storage.s3 import get_storage
from app.workers.celery_app import celery_app

router = APIRouter(prefix="/tenants/{tenant_id}/documents", tags=["documents"])

PDF_MIME = "application/pdf"
INGEST_TASK = "app.workers.tasks.ingest.ingest_document"

_AUDIT_INSERT = text(
    "INSERT INTO audit_logs (tenant_id, user_id, action, entity_type, entity_id, ip)"
    " VALUES (:tenant_id, :user_id, :action, 'document', :entity_id, CAST(:ip AS inet))"
)


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Documento no encontrado")


async def _get_document(db: AsyncSession, ctx: TenantContext, document_id: uuid.UUID) -> Document:
    # tenant_id explícito + RLS: un RESIDENTE pidiendo un documento ADMIN obtiene
    # None (RLS lo oculta) => 404, sin revelar que existe.
    doc = await db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.tenant_id == ctx.tenant_id,
            Document.deleted_at.is_(None),
        )
    )
    if doc is None or (not ctx.is_admin and doc.status != DocumentStatus.READY):
        raise _not_found()
    return doc


async def _latest_job(db: AsyncSession, document_id: uuid.UUID) -> ProcessingJob | None:
    return await db.scalar(
        select(ProcessingJob)
        .where(ProcessingJob.document_id == document_id, ProcessingJob.type == JobType.INGEST)
        .order_by(ProcessingJob.created_at.desc())
        .limit(1)
    )


def _to_out(doc: Document, job: ProcessingJob | None = None) -> DocumentOut:
    out = DocumentOut.model_validate(doc)
    out.job = JobOut.model_validate(job) if job else None
    return out


async def _enqueue_ingestion(db: AsyncSession, ctx: TenantContext, doc: Document) -> ProcessingJob:
    job = ProcessingJob(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        document_id=doc.id,
        type=JobType.INGEST,
        status=JobStatus.PENDING,
        attempts=0,
    )
    doc.status = DocumentStatus.QUEUED
    doc.error_message = None
    db.add(job)
    # COMMIT ANTES DE ENCOLAR: si se encola primero, el worker podría leer la
    # base antes de que exista el job (condición de carrera).
    await db.commit()
    result = await run_in_threadpool(
        celery_app.send_task, INGEST_TASK, args=[str(job.id), str(ctx.tenant_id), str(doc.id)]
    )
    job.celery_task_id = result.id
    await db.commit()
    return job


# ---------------------------------------------------------------------------
# Subida
# ---------------------------------------------------------------------------
@router.post("/uploads", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def create_upload(body: UploadRequest, ctx: AdminCtx, db: DbSession, request: Request) -> UploadResponse:
    await enforce(request, UPLOADS_PER_HOUR, str(ctx.user_id))
    await enforce_demo(request, DEMO_UPLOADS_PER_IP_DAY, demo=ctx.is_demo)
    settings = get_settings()
    if body.size_bytes > settings.max_upload_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"Máximo {settings.max_upload_mb} MB por archivo")
    if not body.filename.lower().endswith(".pdf"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Solo se admiten archivos PDF")

    duplicate = await db.scalar(
        select(Document.id).where(
            Document.tenant_id == ctx.tenant_id,
            Document.sha256 == body.sha256,
            Document.deleted_at.is_(None),
        )
    )
    if duplicate:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"message": "Este archivo ya fue subido", "document_id": str(duplicate)},
        )

    storage = get_storage()
    doc_id = uuid.uuid4()
    access = body.access_level or (AccessLevel.PUBLIC if body.category in PUBLIC_BY_DEFAULT else AccessLevel.ADMIN)
    doc = Document(
        id=doc_id,
        tenant_id=ctx.tenant_id,
        uploaded_by=ctx.user_id,
        title=(body.title or PurePath(body.filename).stem).strip(),
        original_filename=body.filename,
        category=body.category,
        access_level=access,
        status=DocumentStatus.UPLOADED,
        storage_key=storage.document_key(ctx.tenant_id, doc_id, "original.pdf"),
        mime_type=PDF_MIME,
        size_bytes=body.size_bytes,
        sha256=body.sha256,
    )
    db.add(doc)
    try:
        await db.commit()
    except IntegrityError as exc:  # carrera: dos subidas simultáneas del mismo archivo
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Este archivo ya fue subido") from exc

    return UploadResponse(
        document_id=doc_id,
        upload_url=storage.presign_put(doc.storage_key, PDF_MIME),
        headers={"Content-Type": PDF_MIME},
        expires_in=settings.s3_presigned_ttl_seconds,
    )


@router.post("/import/google-drive", response_model=DriveImportResponse)
async def import_from_google_drive(
    body: DriveImportRequest, ctx: AdminCtx, db: DbSession, request: Request
) -> DriveImportResponse:
    """Importa archivos elegidos en el selector de Google Drive.

    A diferencia de la subida directa, aquí el archivo SÍ pasa por la API: se
    descarga de Drive con el token del usuario (alcance drive.file), se valida y
    se guarda en el almacenamiento. Luego sigue la misma ingesta que una subida.
    Cada archivo se procesa por separado: uno que falle no detiene a los demás.
    """
    for _ in body.files:
        await enforce(request, UPLOADS_PER_HOUR, str(ctx.user_id))
        await enforce_demo(request, DEMO_UPLOADS_PER_IP_DAY, demo=ctx.is_demo)
    settings = get_settings()
    storage = get_storage()
    access = body.access_level or (AccessLevel.PUBLIC if body.category in PUBLIC_BY_DEFAULT else AccessLevel.ADMIN)
    resultados: list[DriveImportResult] = []

    async with google_drive.nuevo_cliente() as cliente:
        for ref in dict.fromkeys(f.id for f in body.files):  # sin repetidos, en el orden elegido
            ya = await db.scalar(
                select(Document.id).where(
                    Document.tenant_id == ctx.tenant_id,
                    Document.source == "GOOGLE_DRIVE",
                    Document.source_ref == ref,
                    Document.deleted_at.is_(None),
                )
            )
            if ya:
                resultados.append(
                    DriveImportResult(
                        file_id=ref, nombre=None, estado="DUPLICADO", document_id=ya, mensaje="Ya se había importado"
                    )
                )
                continue
            try:
                archivo = await google_drive.descargar(cliente, body.access_token, ref, settings.max_upload_bytes)
            except google_drive.DriveError as exc:
                resultados.append(DriveImportResult(file_id=ref, nombre=None, estado="ERROR", mensaje=str(exc)))
                continue
            except httpx.HTTPError:
                resultados.append(
                    DriveImportResult(
                        file_id=ref, nombre=None, estado="ERROR", mensaje="No se pudo conectar con Google Drive"
                    )
                )
                continue

            sha = hashlib.sha256(archivo.contenido).hexdigest()
            duplicado = await db.scalar(
                select(Document.id).where(
                    Document.tenant_id == ctx.tenant_id, Document.sha256 == sha, Document.deleted_at.is_(None)
                )
            )
            if duplicado:
                resultados.append(
                    DriveImportResult(
                        file_id=ref,
                        nombre=archivo.nombre,
                        estado="DUPLICADO",
                        document_id=duplicado,
                        mensaje="Este archivo ya estaba en la plataforma",
                    )
                )
                continue

            doc_id = uuid.uuid4()
            doc = Document(
                id=doc_id,
                tenant_id=ctx.tenant_id,
                uploaded_by=ctx.user_id,
                title=PurePath(archivo.nombre).stem.strip()[:255],
                original_filename=archivo.nombre[:255],
                category=body.category,
                access_level=access,
                status=DocumentStatus.UPLOADED,
                storage_key=storage.document_key(ctx.tenant_id, doc_id, "original.pdf"),
                mime_type=PDF_MIME,
                size_bytes=len(archivo.contenido),
                sha256=sha,
                source="GOOGLE_DRIVE",
                source_ref=archivo.id,
                source_url=archivo.url,
            )
            await run_in_threadpool(storage.put_bytes, doc.storage_key, archivo.contenido, PDF_MIME)
            db.add(doc)
            await db.execute(
                _AUDIT_INSERT,
                {
                    "tenant_id": ctx.tenant_id,
                    "user_id": ctx.user_id,
                    "action": "document.import_drive",
                    "entity_id": doc_id,
                    "ip": request.client.host if request.client else None,
                },
            )
            try:
                await _enqueue_ingestion(db, ctx, doc)  # hace commit y encola la ingesta
            except IntegrityError:  # carrera: otra importación del mismo archivo en paralelo
                await db.rollback()
                await run_in_threadpool(storage.delete, doc.storage_key)
                resultados.append(
                    DriveImportResult(
                        file_id=ref,
                        nombre=archivo.nombre,
                        estado="DUPLICADO",
                        mensaje="Este archivo ya estaba en la plataforma",
                    )
                )
                continue
            resultados.append(
                DriveImportResult(file_id=ref, nombre=archivo.nombre, estado="IMPORTADO", document_id=doc_id)
            )

    return DriveImportResponse(resultados=resultados)


@router.post("/{document_id}/complete", response_model=DocumentOut, status_code=status.HTTP_202_ACCEPTED)
async def complete_upload(document_id: uuid.UUID, ctx: AdminCtx, db: DbSession) -> DocumentOut:
    doc = await _get_document(db, ctx, document_id)
    if doc.status != DocumentStatus.UPLOADED:
        raise HTTPException(status.HTTP_409_CONFLICT, f"El documento ya está en estado {doc.status}")

    storage = get_storage()
    size = await run_in_threadpool(storage.object_size, doc.storage_key)
    if size is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "El archivo aún no se ha subido a la URL firmada")

    # La URL firmada no puede limitar el tamaño: se valida aquí contra lo declarado
    # y se comprueba la firma mágica %PDF- (no basta la extensión del nombre).
    problem = None
    if size != doc.size_bytes:
        problem = f"Tamaño subido ({size}) distinto del declarado ({doc.size_bytes})"
    elif not (await run_in_threadpool(storage.read_range, doc.storage_key, 0, 4)).startswith(b"%PDF-"):
        problem = "El archivo no es un PDF"
    if problem:
        await run_in_threadpool(storage.delete, doc.storage_key)
        doc.status = DocumentStatus.FAILED
        doc.error_message = problem
        await db.commit()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, problem)

    job = await _enqueue_ingestion(db, ctx, doc)
    return _to_out(doc, job)


@router.post("/{document_id}/reprocess", response_model=DocumentOut, status_code=status.HTTP_202_ACCEPTED)
async def reprocess(document_id: uuid.UUID, ctx: AdminCtx, db: DbSession) -> DocumentOut:
    """Reintenta un documento FAILED o re-indexa uno READY (p.ej. al cambiar de
    modelo de embeddings)."""
    doc = await _get_document(db, ctx, document_id)
    if doc.status not in {DocumentStatus.FAILED, DocumentStatus.READY}:
        raise HTTPException(status.HTTP_409_CONFLICT, f"No se puede reprocesar en estado {doc.status}")
    if await run_in_threadpool(get_storage().object_size, doc.storage_key) is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "El archivo original ya no existe; súbelo de nuevo")
    job = await _enqueue_ingestion(db, ctx, doc)
    return _to_out(doc, job)


# ---------------------------------------------------------------------------
# Consulta
# ---------------------------------------------------------------------------
@router.get("", response_model=list[DocumentOut])
async def list_documents(
    ctx: TenantCtx,
    db: DbSession,
    category: DocumentCategory | None = None,
    doc_status: DocumentStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[DocumentOut]:
    # Sin filtro por access_level aquí: RLS ya oculta los documentos ADMIN a residentes
    stmt = select(Document).where(Document.tenant_id == ctx.tenant_id, Document.deleted_at.is_(None))
    if category:
        stmt = stmt.where(Document.category == category)
    if not ctx.is_admin:
        stmt = stmt.where(Document.status == DocumentStatus.READY)
    elif doc_status:
        stmt = stmt.where(Document.status == doc_status)
    docs = list(await db.scalars(stmt.order_by(Document.created_at.desc()).limit(limit).offset(offset)))
    jobs: dict[uuid.UUID, ProcessingJob] = {}
    if ctx.is_admin and docs:
        # Último job de ingesta por documento en UNA consulta (DISTINCT ON), para
        # que el frontend muestre el progreso sin pedir cada documento por separado
        latest = await db.scalars(
            select(ProcessingJob)
            .distinct(ProcessingJob.document_id)
            .where(ProcessingJob.document_id.in_([d.id for d in docs]), ProcessingJob.type == JobType.INGEST)
            .order_by(ProcessingJob.document_id, ProcessingJob.created_at.desc())
        )
        jobs = {j.document_id: j for j in latest if j.document_id}
    return [_to_out(d, jobs.get(d.id)) for d in docs]


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(document_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> DocumentOut:
    doc = await _get_document(db, ctx, document_id)
    job = await _latest_job(db, doc.id) if ctx.is_admin else None
    return _to_out(doc, job)


@router.get("/{document_id}/file-url", response_model=FileUrlResponse)
async def file_url(document_id: uuid.UUID, ctx: TenantCtx, db: DbSession, request: Request) -> FileUrlResponse:
    """URL GET firmada de corta duración para el visor PDF. Se prefiere la versión
    con OCR (texto seleccionable) si existe."""
    doc = await _get_document(db, ctx, document_id)
    key = doc.ocr_storage_key or doc.storage_key
    # SQL explícito SIN "RETURNING" a propósito: SQLAlchemy (tanto db.add() como
    # insert() de Core) añade "RETURNING id" para conocer la clave generada, y
    # Postgres aplica a las filas devueltas las políticas de SELECT. Un residente
    # no puede leer audit_logs (append-only), así que RLS rechazaría el INSERT.
    await db.execute(
        _AUDIT_INSERT,
        {
            "tenant_id": ctx.tenant_id,
            "user_id": ctx.user_id,
            "action": "document.view",
            "entity_id": doc.id,
            "ip": request.client.host if request.client else None,
        },
    )
    await db.commit()
    return FileUrlResponse(
        url=get_storage().presign_get(key, doc.original_filename),
        expires_in=get_settings().s3_presigned_ttl_seconds,
        is_ocr_version=doc.ocr_storage_key is not None,
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: uuid.UUID, ctx: AdminCtx, db: DbSession) -> None:
    """Soft delete: deja de aparecer en listados y búsquedas (hybrid_search filtra
    deleted_at). La purga física de S3 y chunks queda para una tarea programada."""
    doc = await _get_document(db, ctx, document_id)
    doc.deleted_at = datetime.now(UTC)
    await db.commit()
