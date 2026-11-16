"""Buscador general con IA.

GET  /search  -> solo recuperación (fragmentos con página), sin LLM
POST /ask     -> respuesta RAG en streaming (SSE) con citas verificadas

Protocolo SSE de /ask (en orden):
  event: sources  {conversation_id, search_query, sources: [{n, document_id, document_name, page_number, ...}]}
  event: token    {text}            (repetido, fragmentos de la respuesta)
  event: done     {message_id, citations: [n...], usage, latency_ms}
  event: error    {message, retryable}   (en lugar de done si el LLM falla)
El frontend convierte cada [n] del texto en un botón que abre el visor PDF en
sources[n].page_number.
"""

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DbSession, TenantContext, TenantCtx
from app.core.config import get_settings
from app.core.rate_limit import (
    ASK_PER_DAY,
    ASK_PER_MINUTE,
    DEMO_ASK_PER_IP_DAY,
    SEARCH_PER_MINUTE,
    enforce,
    enforce_demo,
)
from app.db.rls import set_rls_context
from app.db.session import SessionLocal
from app.models import Conversation, Message, Tenant
from app.models.enums import DocumentCategory, MessageRole
from app.schemas.search import AskRequest, ConversationOut, MessageOut, SearchHit
from app.services.llm.chat import ChatMessage, LLMConfigError, LLMError, Usage, get_chat_model
from app.services.llm.embeddings import EmbeddingConfigError
from app.services.retrieval.prompt import (
    NOT_FOUND_ANSWER,
    build_messages,
    condense_messages,
    parse_citations,
    system_prompt,
)
from app.services.retrieval.search import RetrievedChunk, retrieve

log = logging.getLogger(__name__)
router = APIRouter(prefix="/tenants/{tenant_id}", tags=["search"])

SNIPPET_CHARS = 320


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _source(c: RetrievedChunk) -> dict[str, Any]:
    snippet = c.content if len(c.content) <= SNIPPET_CHARS else c.content[:SNIPPET_CHARS].rsplit(" ", 1)[0] + "…"
    return {
        "n": c.n,
        "chunk_id": c.chunk_id,
        "document_id": c.document_id,
        "document_name": c.document_name,
        "page_number": c.page_number,
        "page_end": c.page_end,
        "category": c.category,
        "section_title": c.section_title,
        "snippet": snippet,
        "content": c.content,  # el visor lo usa para resaltar el fragmento en la página
    }


async def _retrieve(
    db: AsyncSession, ctx: TenantContext, query: str, top_k: int, categories: list[DocumentCategory] | None
) -> list[RetrievedChunk]:
    try:
        return await retrieve(
            db, tenant_id=ctx.tenant_id, is_admin=ctx.is_admin, query=query, top_k=top_k, categories=categories
        )
    except EmbeddingConfigError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Buscador no configurado: {exc}") from exc
    except Exception as exc:  # proveedor de embeddings caído / rate limit
        log.exception("fallo al generar embedding de la consulta")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "El servicio de búsqueda no está disponible") from exc


# ---------------------------------------------------------------------------
# Búsqueda sin LLM
# ---------------------------------------------------------------------------
@router.get("/search", response_model=list[SearchHit])
async def search(
    ctx: TenantCtx,
    db: DbSession,
    request: Request,
    q: str = Query(min_length=2, max_length=500),
    category: list[DocumentCategory] | None = Query(default=None),
    limit: int = Query(default=8, ge=1, le=20),
) -> list[SearchHit]:
    await enforce(request, SEARCH_PER_MINUTE, str(ctx.user_id))
    chunks = await _retrieve(db, ctx, q, limit, category)
    return [
        SearchHit(
            **{k: v for k, v in _source(c).items() if k != "content"},  # type: ignore[arg-type]
            score=c.score,
            semantic_distance=c.semantic_distance,
        )
        for c in chunks
    ]


# ---------------------------------------------------------------------------
# Pregunta con respuesta en streaming
# ---------------------------------------------------------------------------
@router.post("/ask")
async def ask(body: AskRequest, ctx: TenantCtx, db: DbSession, request: Request) -> StreamingResponse:
    await enforce(request, ASK_PER_MINUTE, str(ctx.user_id))
    await enforce(request, ASK_PER_DAY, str(ctx.user_id))
    await enforce_demo(request, DEMO_ASK_PER_IP_DAY)
    started = time.perf_counter()
    settings = get_settings()
    try:
        chat = get_chat_model()
    except LLMConfigError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"IA no configurada: {exc}") from exc

    # 1. Conversación (RLS: solo las propias del usuario son visibles)
    if body.conversation_id:
        conversation = await db.get(Conversation, body.conversation_id)
        if conversation is None or conversation.tenant_id != ctx.tenant_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversación no encontrada")
        recent = await db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at.desc())
            .limit(settings.chat_history_messages)
        )
        history = [ChatMessage(role=m.role.value, content=m.content) for m in reversed(list(recent))]  # type: ignore[arg-type]
    else:
        conversation = Conversation(
            id=uuid.uuid4(), tenant_id=ctx.tenant_id, user_id=ctx.user_id, title=body.question[:80]
        )
        db.add(conversation)
        history = []

    # 2. Pregunta de seguimiento ("¿y los gatos?") -> pregunta autónoma para el buscador
    search_query = body.question
    if history:
        try:
            system, msgs = condense_messages(body.question, history)
            search_query = (await chat.complete(system, msgs)) or body.question
        except LLMError:
            log.warning("no se pudo reescribir la pregunta; se usa la original")

    # 3. Recuperación híbrida filtrada por tenant + rol
    chunks = await _retrieve(db, ctx, search_query, settings.retrieval_top_k, body.categories)

    # 4. Se guarda la pregunta ANTES de llamar al LLM (queda aunque el LLM falle)
    db.add(
        Message(
            id=uuid.uuid4(),
            tenant_id=ctx.tenant_id,
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content=body.question,
            citations=[],
        )
    )
    tenant_name = await db.scalar(select(Tenant.name).where(Tenant.id == ctx.tenant_id)) or ""
    await db.commit()

    sources = [_source(c) for c in chunks]
    system = system_prompt(tenant_name, ctx.role)
    messages = build_messages(body.question, chunks, history)
    conversation_id = conversation.id

    async def event_stream() -> AsyncIterator[str]:
        yield _sse("sources", {"conversation_id": conversation_id, "search_query": search_query, "sources": sources})

        usage = Usage()
        answer = ""
        if not chunks:
            # Sin fragmentos no se llama al LLM: respuesta fija, cero coste, cero alucinación
            answer = NOT_FOUND_ANSWER
            yield _sse("token", {"text": answer})
        else:
            try:
                async for delta in chat.stream(system, messages, usage):
                    answer += delta
                    yield _sse("token", {"text": delta})
            except LLMError as exc:
                log.warning("fallo del LLM: %s", exc)
                yield _sse(
                    "error",
                    {
                        "message": "El asistente no está disponible en este momento. Intenta de nuevo en unos segundos."
                        if exc.retryable
                        else "No se pudo generar la respuesta.",
                        "retryable": exc.retryable,
                    },
                )
                return

        cited = parse_citations(answer, len(chunks))
        latency_ms = int((time.perf_counter() - started) * 1000)
        message_id = uuid.uuid4()

        # La sesión de la petición ya no es fiable dentro del stream: sesión propia
        async with SessionLocal() as stream_db:
            await set_rls_context(stream_db, tenant_id=ctx.tenant_id, user_id=ctx.user_id, role=ctx.role.value)
            stream_db.add(
                Message(
                    id=message_id,
                    tenant_id=ctx.tenant_id,
                    conversation_id=conversation_id,
                    role=MessageRole.ASSISTANT,
                    content=answer,
                    citations=[
                        {
                            k: str(v) if isinstance(v, uuid.UUID) else v
                            for k, v in sources[n - 1].items()
                            if k not in {"snippet", "content"}
                        }
                        for n in cited
                    ],
                    retrieval_trace={
                        "search_query": search_query,
                        "chunks": [
                            {
                                "n": c.n,
                                "chunk_id": str(c.chunk_id),
                                "score": c.score,
                                "semantic_distance": c.semantic_distance,
                                "lexical_rank": c.lexical_rank,
                            }
                            for c in chunks
                        ],
                    },
                    model=chat.model if chunks else None,
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                    latency_ms=latency_ms,
                )
            )
            await stream_db.commit()

        yield _sse(
            "done",
            {
                "message_id": message_id,
                "citations": cited,
                "usage": {"prompt_tokens": usage.prompt_tokens, "completion_tokens": usage.completion_tokens},
                "latency_ms": latency_ms,
            },
        )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},  # sin buffering en proxies
    )


# ---------------------------------------------------------------------------
# Historial
# ---------------------------------------------------------------------------
@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    ctx: TenantCtx, db: DbSession, limit: int = Query(default=30, ge=1, le=100)
) -> list[Conversation]:
    rows = await db.scalars(
        select(Conversation)
        .where(Conversation.tenant_id == ctx.tenant_id, Conversation.user_id == ctx.user_id)
        .order_by(Conversation.created_at.desc())
        .limit(limit)
    )
    return list(rows)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def conversation_messages(conversation_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> list[Message]:
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None or conversation.tenant_id != ctx.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversación no encontrada")
    rows = await db.scalars(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at)
    )
    return list(rows)
