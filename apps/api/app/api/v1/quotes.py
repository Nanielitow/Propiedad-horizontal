"""Comparador de cotizaciones (solo administración; RLS admin_only lo refuerza)."""

import uuid

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminCtx, DbSession, TenantContext
from app.core.rate_limit import AI_JOBS_PER_DAY, enforce
from app.models import Document, QuoteComparison, QuoteComparisonDocument
from app.models.enums import DocumentStatus, JobStatus
from app.schemas.quote import ComparisonCreate, ComparisonDocumentOut, ComparisonOut, ComparisonSummary
from app.services.extraction.quotes import COMPARE_TASK
from app.workers.celery_app import celery_app

router = APIRouter(prefix="/tenants/{tenant_id}/quote-comparisons", tags=["quotes"])


async def _enqueue(db: AsyncSession, comparison: QuoteComparison) -> None:
    await db.commit()  # commit ANTES de encolar
    await run_in_threadpool(celery_app.send_task, COMPARE_TASK, args=[str(comparison.id), str(comparison.tenant_id)])


async def _detail(db: AsyncSession, ctx: TenantContext, comparison_id: uuid.UUID) -> ComparisonOut:
    comparison = await db.scalar(
        select(QuoteComparison).where(QuoteComparison.id == comparison_id, QuoteComparison.tenant_id == ctx.tenant_id)
    )
    if comparison is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Comparación no encontrada")
    rows = (
        await db.execute(
            select(QuoteComparisonDocument, Document.title)
            .join(Document, Document.id == QuoteComparisonDocument.document_id)
            .where(QuoteComparisonDocument.comparison_id == comparison_id)
            .order_by(Document.title)
        )
    ).all()
    result = comparison.result or {}
    return ComparisonOut(
        id=comparison.id,
        title=comparison.title,
        status=comparison.status,
        created_at=comparison.created_at,
        model=comparison.model,
        progress=result.get("progress"),
        error=result.get("error"),
        best=result.get("best"),
        analysis=result.get("analysis"),
        documents=[
            ComparisonDocumentOut(
                document_id=link.document_id,
                document_title=title,
                provider_name=link.provider_name,
                extracted=link.extracted,
            )
            for link, title in rows
        ],
    )


@router.get("", response_model=list[ComparisonSummary])
async def list_comparisons(
    ctx: AdminCtx, db: DbSession, limit: int = Query(default=50, le=200)
) -> list[ComparisonSummary]:
    comparisons = list(
        await db.scalars(
            select(QuoteComparison)
            .where(QuoteComparison.tenant_id == ctx.tenant_id)
            .order_by(QuoteComparison.created_at.desc())
            .limit(limit)
        )
    )
    providers: dict[uuid.UUID, list[str]] = {c.id: [] for c in comparisons}
    if comparisons:
        for link, title in await db.execute(
            select(QuoteComparisonDocument, Document.title)
            .join(Document, Document.id == QuoteComparisonDocument.document_id)
            .where(QuoteComparisonDocument.comparison_id.in_(list(providers)))
        ):
            providers[link.comparison_id].append(link.provider_name or title)
    return [
        ComparisonSummary(
            id=c.id,
            title=c.title,
            status=c.status,
            created_at=c.created_at,
            providers=sorted(providers[c.id]),
            min_total=((c.result or {}).get("best") or {}).get("min_total"),
            progress=(c.result or {}).get("progress"),
        )
        for c in comparisons
    ]


@router.post("", response_model=ComparisonOut, status_code=status.HTTP_201_CREATED)
async def create_comparison(body: ComparisonCreate, ctx: AdminCtx, db: DbSession, request: Request) -> ComparisonOut:
    await enforce(request, AI_JOBS_PER_DAY, str(ctx.tenant_id))
    docs = list(
        await db.scalars(
            select(Document).where(
                Document.id.in_(body.document_ids), Document.tenant_id == ctx.tenant_id, Document.deleted_at.is_(None)
            )
        )
    )
    if len(docs) != len(body.document_ids):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alguna cotización no existe")
    not_ready = [d.title for d in docs if d.status != DocumentStatus.READY]
    if not_ready:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Aún se están procesando: {', '.join(not_ready)}")

    comparison = QuoteComparison(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        created_by=ctx.user_id,
        title=body.title.strip(),
        status=JobStatus.PENDING,
        result={"progress": "queued"},
    )
    db.add(comparison)
    await db.flush()
    for d in docs:
        db.add(QuoteComparisonDocument(tenant_id=ctx.tenant_id, comparison_id=comparison.id, document_id=d.id))
    await _enqueue(db, comparison)
    return await _detail(db, ctx, comparison.id)


@router.get("/{comparison_id}", response_model=ComparisonOut)
async def get_comparison(comparison_id: uuid.UUID, ctx: AdminCtx, db: DbSession) -> ComparisonOut:
    return await _detail(db, ctx, comparison_id)


@router.post("/{comparison_id}/retry", response_model=ComparisonOut)
async def retry_comparison(comparison_id: uuid.UUID, ctx: AdminCtx, db: DbSession, request: Request) -> ComparisonOut:
    await enforce(request, AI_JOBS_PER_DAY, str(ctx.tenant_id))
    comparison = await db.scalar(
        select(QuoteComparison).where(QuoteComparison.id == comparison_id, QuoteComparison.tenant_id == ctx.tenant_id)
    )
    if comparison is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Comparación no encontrada")
    if comparison.status in {JobStatus.PENDING, JobStatus.RUNNING, JobStatus.RETRYING}:
        raise HTTPException(status.HTTP_409_CONFLICT, "La comparación ya se está procesando")
    comparison.status = JobStatus.PENDING
    comparison.result = {"progress": "queued"}
    await _enqueue(db, comparison)
    return await _detail(db, ctx, comparison_id)


@router.delete("/{comparison_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comparison(comparison_id: uuid.UUID, ctx: AdminCtx, db: DbSession) -> None:
    result = await db.execute(
        delete(QuoteComparison).where(QuoteComparison.id == comparison_id, QuoteComparison.tenant_id == ctx.tenant_id)
    )
    if not result.rowcount:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Comparación no encontrada")
    await db.commit()
