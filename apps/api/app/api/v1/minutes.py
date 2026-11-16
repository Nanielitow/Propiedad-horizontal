"""Actas: resúmenes y tareas de seguimiento (solo administración; RLS admin_only)."""

import uuid
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminCtx, DbSession, TenantContext
from app.core.rate_limit import AI_JOBS_PER_DAY, enforce
from app.models import ActionItem, Document, MinutesSummary, ProcessingJob
from app.models.enums import DocumentCategory, DocumentStatus, JobStatus, JobType, TaskStatus
from app.services.extraction.minutes import SUMMARIZE_TASK
from app.workers.celery_app import celery_app

router = APIRouter(prefix="/tenants/{tenant_id}/minutes", tags=["minutes"])

RUNNING = {JobStatus.PENDING, JobStatus.RUNNING, JobStatus.RETRYING}


# -- Esquemas -------------------------------------------------------------------
class ActaOut(BaseModel):
    document_id: uuid.UUID
    title: str
    document_date: date | None
    created_at: datetime
    status: str  # NONE | PROCESSING | READY | FAILED
    error: str | None
    assembly_type: str | None
    assembly_date: date | None
    quorum_pct: float | None
    agreements: int
    votes: int
    open_tasks: int


class TaskOut(BaseModel):
    id: uuid.UUID
    description: str
    assignee: str | None
    due_date: date | None
    status: TaskStatus
    source_page: int | None
    document_id: uuid.UUID
    document_title: str


class MinutesDetail(BaseModel):
    document_id: uuid.UUID
    title: str
    status: str
    error: str | None
    assembly_type: str | None
    assembly_date: date | None
    quorum_pct: float | None
    summary: str | None
    agreements: list[dict[str, Any]]
    votes: list[dict[str, Any]]
    model: str | None
    tasks: list[TaskOut]


class TaskUpdate(BaseModel):
    status: TaskStatus | None = None
    assignee: str | None = None
    due_date: date | None = None


# -- Utilidades -----------------------------------------------------------------
async def _latest_jobs(db: AsyncSession, doc_ids: list[uuid.UUID]) -> dict[uuid.UUID, ProcessingJob]:
    if not doc_ids:
        return {}
    jobs = await db.scalars(
        select(ProcessingJob)
        .distinct(ProcessingJob.document_id)
        .where(ProcessingJob.document_id.in_(doc_ids), ProcessingJob.type == JobType.SUMMARIZE_MINUTES)
        .order_by(ProcessingJob.document_id, ProcessingJob.created_at.desc())
    )
    return {j.document_id: j for j in jobs if j.document_id}


def _state(job: ProcessingJob | None, has_summary: bool) -> tuple[str, str | None]:
    if job and job.status in RUNNING:
        return "PROCESSING", None
    if has_summary:
        return "READY", None
    if job and job.status == JobStatus.FAILED:
        return "FAILED", job.error
    return "NONE", None


async def _tasks(db: AsyncSession, ctx: TenantContext, document_id: uuid.UUID | None = None) -> list[TaskOut]:
    stmt = (
        select(ActionItem, Document.id, Document.title)
        .join(MinutesSummary, MinutesSummary.id == ActionItem.minutes_summary_id)
        .join(Document, Document.id == MinutesSummary.document_id)
        .where(ActionItem.tenant_id == ctx.tenant_id, Document.deleted_at.is_(None))
        .order_by(ActionItem.status, ActionItem.due_date.asc().nulls_last())
    )
    if document_id:
        stmt = stmt.where(Document.id == document_id)
    return [
        TaskOut(
            id=t.id,
            description=t.description,
            assignee=t.assignee,
            due_date=t.due_date,
            status=t.status,
            source_page=t.source_page,
            document_id=doc_id,
            document_title=title,
        )
        for t, doc_id, title in await db.execute(stmt)
    ]


# -- Tareas (antes de /{document_id} para que "tasks" no se tome como id) ---------
@router.get("/tasks", response_model=list[TaskOut])
async def list_tasks(ctx: AdminCtx, db: DbSession) -> list[TaskOut]:
    return await _tasks(db, ctx)


@router.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(task_id: uuid.UUID, body: TaskUpdate, ctx: AdminCtx, db: DbSession) -> TaskOut:
    task = await db.scalar(select(ActionItem).where(ActionItem.id == task_id, ActionItem.tenant_id == ctx.tenant_id))
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tarea no encontrada")
    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "status" and value is None:
            continue
        setattr(task, field, value)
    await db.commit()
    return next(t for t in await _tasks(db, ctx) if t.id == task_id)


# -- Actas ------------------------------------------------------------------------
@router.get("", response_model=list[ActaOut])
async def list_minutes(ctx: AdminCtx, db: DbSession) -> list[ActaOut]:
    docs = list(
        await db.scalars(
            select(Document)
            .where(
                Document.tenant_id == ctx.tenant_id,
                Document.category == DocumentCategory.ACTAS,
                Document.status == DocumentStatus.READY,
                Document.deleted_at.is_(None),
            )
            .order_by(func.coalesce(Document.document_date, func.date(Document.created_at)).desc())
        )
    )
    ids = [d.id for d in docs]
    summaries = (
        {s.document_id: s for s in await db.scalars(select(MinutesSummary).where(MinutesSummary.document_id.in_(ids)))}
        if ids
        else {}
    )
    open_counts: dict[uuid.UUID, int] = {}
    if summaries:
        rows = await db.execute(
            select(ActionItem.minutes_summary_id, func.count())
            .where(
                ActionItem.minutes_summary_id.in_([s.id for s in summaries.values()]),
                ActionItem.status != TaskStatus.DONE,
            )
            .group_by(ActionItem.minutes_summary_id)
        )
        open_counts = {sid: n for sid, n in rows}
    jobs = await _latest_jobs(db, ids)

    out = []
    for d in docs:
        s = summaries.get(d.id)
        state, error = _state(jobs.get(d.id), s is not None)
        out.append(
            ActaOut(
                document_id=d.id,
                title=d.title,
                document_date=d.document_date,
                created_at=d.created_at,
                status=state,
                error=error,
                assembly_type=s.assembly_type if s else None,
                assembly_date=s.assembly_date if s else None,
                quorum_pct=float(s.quorum_pct) if s and s.quorum_pct is not None else None,
                agreements=len(s.agreements) if s else 0,
                votes=len(s.votes) if s else 0,
                open_tasks=open_counts.get(s.id, 0) if s else 0,
            )
        )
    return out


@router.get("/{document_id}", response_model=MinutesDetail)
async def get_minutes(document_id: uuid.UUID, ctx: AdminCtx, db: DbSession) -> MinutesDetail:
    doc = await db.scalar(
        select(Document).where(
            Document.id == document_id, Document.tenant_id == ctx.tenant_id, Document.deleted_at.is_(None)
        )
    )
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Acta no encontrada")
    s = await db.scalar(select(MinutesSummary).where(MinutesSummary.document_id == document_id))
    state, error = _state((await _latest_jobs(db, [document_id])).get(document_id), s is not None)
    return MinutesDetail(
        document_id=doc.id,
        title=doc.title,
        status=state,
        error=error,
        assembly_type=s.assembly_type if s else None,
        assembly_date=s.assembly_date if s else None,
        quorum_pct=float(s.quorum_pct) if s and s.quorum_pct is not None else None,
        summary=s.summary if s else None,
        agreements=s.agreements if s else [],
        votes=s.votes if s else [],
        model=s.model if s else None,
        tasks=await _tasks(db, ctx, document_id),
    )


@router.post("/{document_id}/summarize", status_code=status.HTTP_202_ACCEPTED)
async def summarize(document_id: uuid.UUID, ctx: AdminCtx, db: DbSession, request: Request) -> dict[str, str]:
    await enforce(request, AI_JOBS_PER_DAY, str(ctx.tenant_id))
    doc = await db.scalar(
        select(Document).where(
            Document.id == document_id, Document.tenant_id == ctx.tenant_id, Document.deleted_at.is_(None)
        )
    )
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Acta no encontrada")
    if doc.status != DocumentStatus.READY:
        raise HTTPException(status.HTTP_409_CONFLICT, "El acta aún no termina de procesarse")
    job = (await _latest_jobs(db, [document_id])).get(document_id)
    if job and job.status in RUNNING:
        raise HTTPException(status.HTTP_409_CONFLICT, "El acta ya se está resumiendo")
    new_job = ProcessingJob(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        document_id=document_id,
        type=JobType.SUMMARIZE_MINUTES,
        status=JobStatus.PENDING,
        attempts=0,
        payload={},
    )
    db.add(new_job)
    await db.commit()  # commit antes de encolar
    result = await run_in_threadpool(
        celery_app.send_task, SUMMARIZE_TASK, args=[str(new_job.id), str(ctx.tenant_id), str(document_id)]
    )
    new_job.celery_task_id = result.id
    await db.commit()
    return {"job_id": str(new_job.id)}
