"""Vencimientos (solo administración; RLS admin_only lo refuerza en la base)."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminCtx, DbSession, TenantContext
from app.core.rate_limit import AI_JOBS_PER_DAY, enforce
from app.models import Deadline, Document, ProcessingJob
from app.models.enums import DeadlineStatus, DocumentStatus, JobStatus, JobType
from app.schemas.deadline import (
    AnalyzingDocument,
    CompleteResponse,
    DeadlineOut,
    DeadlinesResponse,
    DeadlineUpdate,
    ScanRequest,
)
from app.services.extraction.deadlines import EXTRACT_TASK, add_months
from app.workers.celery_app import celery_app

router = APIRouter(prefix="/tenants/{tenant_id}/deadlines", tags=["deadlines"])


def _out(d: Deadline, document_title: str) -> DeadlineOut:
    return DeadlineOut(
        id=d.id,
        document_id=d.document_id,
        document_title=document_title,
        title=d.title,
        type=d.type,
        status=d.status,
        due_date=d.due_date,
        start_date=d.start_date,
        recurrence_months=d.recurrence_months,
        provider_name=d.provider_name,
        source_page=d.source_page,
        source_quote=d.source_quote,
        confidence=float(d.confidence) if d.confidence is not None else None,
        reminder_days=list(d.reminder_days or []),
        reviewed_at=d.reviewed_at,
        created_at=d.created_at,
    )


async def _get(db: AsyncSession, ctx: TenantContext, deadline_id: uuid.UUID) -> tuple[Deadline, str]:
    row = (
        await db.execute(
            select(Deadline, Document.title)
            .join(Document, Document.id == Deadline.document_id)
            .where(Deadline.id == deadline_id, Deadline.tenant_id == ctx.tenant_id)
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vencimiento no encontrado")
    return row[0], row[1]


@router.get("", response_model=DeadlinesResponse)
async def list_deadlines(
    ctx: AdminCtx, db: DbSession, include_dismissed: bool = Query(default=False)
) -> DeadlinesResponse:
    stmt = (
        select(Deadline, Document.title)
        .join(Document, Document.id == Deadline.document_id)
        .where(Deadline.tenant_id == ctx.tenant_id, Document.deleted_at.is_(None))
        .order_by(Deadline.due_date)
    )
    if not include_dismissed:
        stmt = stmt.where(Deadline.status != DeadlineStatus.DISMISSED)
    rows = (await db.execute(stmt)).all()

    jobs = (
        await db.execute(
            select(ProcessingJob.document_id, Document.title, ProcessingJob.status)
            .join(Document, Document.id == ProcessingJob.document_id)
            .where(
                ProcessingJob.tenant_id == ctx.tenant_id,
                ProcessingJob.type == JobType.EXTRACT_DEADLINES,
                ProcessingJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING, JobStatus.RETRYING]),
                Document.deleted_at.is_(None),
            )
        )
    ).all()
    return DeadlinesResponse(
        deadlines=[_out(d, title) for d, title in rows],
        analyzing=[AnalyzingDocument(document_id=j[0], title=j[1], status=j[2].value) for j in jobs],
    )


@router.patch("/{deadline_id}", response_model=DeadlineOut)
async def update_deadline(deadline_id: uuid.UUID, body: DeadlineUpdate, ctx: AdminCtx, db: DbSession) -> DeadlineOut:
    deadline, doc_title = await _get(db, ctx, deadline_id)
    changes = body.model_dump(exclude_unset=True)  # solo lo enviado; permite poner null explícito
    for field in ("title", "type", "due_date", "provider_name", "recurrence_months", "reminder_days"):
        if field in changes:
            setattr(deadline, field, changes[field])
    if "status" in changes and changes["status"] is not None:
        deadline.status = changes["status"]
        # Confirmar o descartar = revisión humana: queda registrado quién y cuándo
        if deadline.status in {DeadlineStatus.ACTIVE, DeadlineStatus.DISMISSED}:
            deadline.reviewed_by = ctx.user_id
            deadline.reviewed_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(deadline)
    return _out(deadline, doc_title)


@router.post("/{deadline_id}/complete", response_model=CompleteResponse)
async def complete_deadline(deadline_id: uuid.UUID, ctx: AdminCtx, db: DbSession) -> CompleteResponse:
    """Marca como renovado/realizado. Si es periódico (p. ej. lavado de tanques cada
    6 meses), crea automáticamente la siguiente fecha ya confirmada."""
    deadline, doc_title = await _get(db, ctx, deadline_id)
    if deadline.status == DeadlineStatus.DONE:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya estaba marcado como realizado")
    deadline.status = DeadlineStatus.DONE
    deadline.reviewed_by = ctx.user_id
    deadline.reviewed_at = datetime.now(UTC)

    next_deadline = None
    if deadline.recurrence_months:
        next_deadline = Deadline(
            id=uuid.uuid4(),
            tenant_id=ctx.tenant_id,
            document_id=deadline.document_id,
            title=deadline.title,
            type=deadline.type,
            status=DeadlineStatus.ACTIVE,
            due_date=add_months(deadline.due_date, deadline.recurrence_months),
            start_date=deadline.due_date,
            recurrence_months=deadline.recurrence_months,
            provider_name=deadline.provider_name,
            source_page=deadline.source_page,
            source_quote=deadline.source_quote,
            confidence=deadline.confidence,
            reminder_days=list(deadline.reminder_days or []),
            reviewed_by=ctx.user_id,
            reviewed_at=datetime.now(UTC),
        )
        db.add(next_deadline)
    await db.commit()
    await db.refresh(deadline)
    if next_deadline:
        await db.refresh(next_deadline)
    return CompleteResponse(
        completed=_out(deadline, doc_title), next=_out(next_deadline, doc_title) if next_deadline else None
    )


@router.post("/scan", status_code=status.HTTP_202_ACCEPTED)
async def scan_document(body: ScanRequest, ctx: AdminCtx, db: DbSession, request: Request) -> dict[str, str]:
    """Vuelve a buscar vencimientos en un documento ya procesado."""
    await enforce(request, AI_JOBS_PER_DAY, str(ctx.tenant_id))
    doc = await db.scalar(
        select(Document).where(
            Document.id == body.document_id, Document.tenant_id == ctx.tenant_id, Document.deleted_at.is_(None)
        )
    )
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento no encontrado")
    if doc.status != DocumentStatus.READY:
        raise HTTPException(status.HTTP_409_CONFLICT, "El documento aún no termina de procesarse")
    job = ProcessingJob(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        document_id=doc.id,
        type=JobType.EXTRACT_DEADLINES,
        status=JobStatus.PENDING,
        attempts=0,
        payload={},
    )
    db.add(job)
    await db.commit()  # commit antes de encolar
    result = await run_in_threadpool(
        celery_app.send_task, EXTRACT_TASK, args=[str(job.id), str(ctx.tenant_id), str(doc.id)]
    )
    job.celery_task_id = result.id
    await db.commit()
    return {"job_id": str(job.id)}
