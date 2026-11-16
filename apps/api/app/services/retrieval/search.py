"""Recuperación híbrida (vector + palabras clave) filtrada por tenant y rol."""

import uuid
from dataclasses import dataclass

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import DocumentCategory
from app.services.llm.embeddings import get_embedder

_HYBRID_SEARCH = text(
    """
    SELECT * FROM hybrid_search(
        :tenant_id,
        :is_admin,
        CAST(CAST(:embedding AS text) AS vector),
        :query,
        :top_k,
        CAST(CAST(:categories AS text[]) AS document_category[]),
        60,
        :embedding_model
    )
    """
)


@dataclass(frozen=True)
class RetrievedChunk:
    n: int  # número de cita [n] que verá el LLM (1-based)
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    page_number: int
    page_end: int
    category: str
    section_title: str | None
    content: str
    score: float
    semantic_distance: float | None
    semantic_rank: int | None
    lexical_rank: int | None


def _vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{v:.7f}" for v in vec) + "]"


async def retrieve(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    is_admin: bool,
    query: str,
    top_k: int,
    categories: list[DocumentCategory] | None = None,
) -> list[RetrievedChunk]:
    embedder = get_embedder()
    vector = await run_in_threadpool(embedder.embed_query, query)

    # Parámetros del índice HNSW, solo para esta transacción:
    # - ef_search: tamaño de la lista de candidatos (recall frente a velocidad)
    # - iterative_scan: si los filtros (tenant, rol) descartan candidatos, sigue
    #   recorriendo el índice hasta completar el top-k (pgvector >= 0.8)
    await db.execute(text("SET LOCAL hnsw.ef_search = 100"))
    await db.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))

    rows = await db.execute(
        _HYBRID_SEARCH,
        {
            "tenant_id": tenant_id,
            "is_admin": is_admin,
            "embedding": _vector_literal(vector),
            "query": query,
            "top_k": top_k,
            "categories": [c.value for c in categories] if categories else None,
            "embedding_model": embedder.model,
        },
    )
    return [
        RetrievedChunk(
            n=i,
            chunk_id=r.chunk_id,
            document_id=r.document_id,
            document_name=r.document_name,
            page_number=r.page_number,
            page_end=r.page_end,
            category=str(r.category),
            section_title=r.section_title,
            content=r.content,
            score=float(r.score),
            semantic_distance=r.semantic_distance,
            semantic_rank=r.semantic_rank,
            lexical_rank=r.lexical_rank,
        )
        for i, r in enumerate(rows, start=1)
    ]
