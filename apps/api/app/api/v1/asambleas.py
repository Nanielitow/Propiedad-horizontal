"""API del módulo de asambleas (docs/ASAMBLEAS.md).

El detalle se consulta con frecuencia (cada pocos segundos) durante la asamblea: devuelve el
quórum, el resultado parcial del punto en votación y el padrón con la asistencia.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Request, Response, status
from fastapi.concurrency import run_in_threadpool

from app.api.deps import DbSession, TenantCtx
from app.api.v1.documents import _enqueue_ingestion
from app.core.rate_limit import PORTAL_WRITES_PER_MINUTE as LIMITE
from app.core.rate_limit import enforce
from app.schemas.asambleas import (
    AbrirIn,
    AsambleaIn,
    AsambleaUpdate,
    AsistenciaIn,
    CancelarIn,
    CerrarIn,
    ConvocarIn,
    PuntoIn,
    PuntoUpdate,
    VotoPortalIn,
    VotoSalaIn,
)
from app.schemas.asambleas_out import AsambleaDetalle, AsambleaResumen
from app.services.asambleas import acta, consultas
from app.services.asambleas import servicio as s
from app.workers.celery_app import celery_app

router = APIRouter(prefix="/tenants/{tenant_id}/asambleas", tags=["asambleas"])


async def _detalle(db: DbSession, ctx: TenantCtx, asamblea_id: uuid.UUID) -> AsambleaDetalle:
    return await consultas.detalle(db, ctx, asamblea_id)


@router.get("", response_model=list[AsambleaResumen])
async def listar(ctx: TenantCtx, db: DbSession) -> list[AsambleaResumen]:
    return await consultas.listar(db, ctx)


@router.post("", response_model=AsambleaDetalle, status_code=status.HTTP_201_CREATED)
async def crear(body: AsambleaIn, ctx: TenantCtx, db: DbSession) -> AsambleaDetalle:
    a = await s.crear(db, ctx, body)
    await db.commit()
    return await _detalle(db, ctx, a.id)


@router.get("/{asamblea_id}", response_model=AsambleaDetalle)
async def detalle(asamblea_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> AsambleaDetalle:
    return await _detalle(db, ctx, asamblea_id)


@router.patch("/{asamblea_id}", response_model=AsambleaDetalle)
async def editar(asamblea_id: uuid.UUID, body: AsambleaUpdate, ctx: TenantCtx, db: DbSession) -> AsambleaDetalle:
    await s.editar(db, ctx, asamblea_id, body)
    await db.commit()
    return await _detalle(db, ctx, asamblea_id)


@router.post("/{asamblea_id}/puntos", response_model=AsambleaDetalle, status_code=status.HTTP_201_CREATED)
async def agregar_punto(asamblea_id: uuid.UUID, body: PuntoIn, ctx: TenantCtx, db: DbSession) -> AsambleaDetalle:
    await s.agregar_punto(db, ctx, asamblea_id, body)
    await db.commit()
    return await _detalle(db, ctx, asamblea_id)


@router.patch("/puntos/{punto_id}", response_model=AsambleaDetalle)
async def editar_punto(punto_id: uuid.UUID, body: PuntoUpdate, ctx: TenantCtx, db: DbSession) -> AsambleaDetalle:
    p = await s.editar_punto(db, ctx, punto_id, body)
    await db.commit()
    return await _detalle(db, ctx, p.asamblea_id)


@router.delete("/puntos/{punto_id}", response_model=AsambleaDetalle)
async def quitar_punto(punto_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> AsambleaDetalle:
    p = await s.punto(db, ctx, punto_id)
    asamblea_id = p.asamblea_id
    await s.quitar_punto(db, ctx, punto_id)
    await db.commit()
    return await _detalle(db, ctx, asamblea_id)


@router.post("/{asamblea_id}/convocar", response_model=None)
async def convocar(asamblea_id: uuid.UUID, body: ConvocarIn, ctx: TenantCtx, db: DbSession) -> dict[str, Any]:
    a, aviso = await s.convocar(db, ctx, asamblea_id, body)
    await db.commit()
    if body.enviar_correo and a.circular_id:
        await run_in_threadpool(
            celery_app.send_task, "portal.circular_publicada", args=[str(ctx.tenant_id), str(a.circular_id)]
        )
    return {"asamblea": (await _detalle(db, ctx, asamblea_id)).model_dump(mode="json"), "aviso": aviso}


@router.post("/{asamblea_id}/cancelar", response_model=AsambleaDetalle)
async def cancelar(asamblea_id: uuid.UUID, body: CancelarIn, ctx: TenantCtx, db: DbSession) -> AsambleaDetalle:
    await s.cancelar(db, ctx, asamblea_id, body)
    await db.commit()
    return await _detalle(db, ctx, asamblea_id)


@router.post("/{asamblea_id}/abrir", response_model=AsambleaDetalle)
async def abrir(asamblea_id: uuid.UUID, body: AbrirIn, ctx: TenantCtx, db: DbSession) -> AsambleaDetalle:
    await s.abrir(db, ctx, asamblea_id, body)
    await db.commit()
    return await _detalle(db, ctx, asamblea_id)


# --- Asistencia --------------------------------------------------------------------------------


@router.post("/{asamblea_id}/asistencias", response_model=AsambleaDetalle, status_code=status.HTTP_201_CREATED)
async def registrar_asistencia(
    asamblea_id: uuid.UUID, body: AsistenciaIn, ctx: TenantCtx, db: DbSession
) -> AsambleaDetalle:
    await s.registrar_asistencia(db, ctx, asamblea_id, body)
    await db.commit()
    return await _detalle(db, ctx, asamblea_id)


@router.post("/{asamblea_id}/asistir", response_model=AsambleaDetalle)
async def asistir_desde_portal(
    asamblea_id: uuid.UUID, request: Request, ctx: TenantCtx, db: DbSession
) -> AsambleaDetalle:
    await enforce(request, LIMITE, str(ctx.user_id))
    await s.asistir_desde_portal(db, ctx, asamblea_id)
    await db.commit()
    return await _detalle(db, ctx, asamblea_id)


@router.post("/asistencias/{asistencia_id}/retiro", response_model=AsambleaDetalle)
async def retirar(asistencia_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> AsambleaDetalle:
    x = await s.retirar(db, ctx, asistencia_id)
    await db.commit()
    return await _detalle(db, ctx, x.asamblea_id)


# --- Votaciones ---------------------------------------------------------------------------------


@router.post("/puntos/{punto_id}/abrir", response_model=AsambleaDetalle)
async def abrir_votacion(punto_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> AsambleaDetalle:
    p = await s.abrir_votacion(db, ctx, punto_id)
    await db.commit()
    return await _detalle(db, ctx, p.asamblea_id)


@router.post("/puntos/{punto_id}/votos", response_model=AsambleaDetalle)
async def votar_en_sala(punto_id: uuid.UUID, body: VotoSalaIn, ctx: TenantCtx, db: DbSession) -> AsambleaDetalle:
    v = await s.votar_en_sala(db, ctx, punto_id, body)
    await db.commit()
    return await _detalle(db, ctx, v.asamblea_id)


@router.post("/puntos/{punto_id}/votar", response_model=AsambleaDetalle)
async def votar_desde_portal(
    punto_id: uuid.UUID, body: VotoPortalIn, request: Request, ctx: TenantCtx, db: DbSession
) -> AsambleaDetalle:
    await enforce(request, LIMITE, str(ctx.user_id))
    votos = await s.votar_desde_portal(db, ctx, punto_id, body)
    await db.commit()
    return await _detalle(db, ctx, votos[0].asamblea_id)


@router.post("/puntos/{punto_id}/cerrar", response_model=AsambleaDetalle)
async def cerrar_punto(punto_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> AsambleaDetalle:
    p = await s.cerrar_punto(db, ctx, punto_id)
    await db.commit()
    return await _detalle(db, ctx, p.asamblea_id)


@router.post("/{asamblea_id}/cerrar", response_model=AsambleaDetalle)
async def cerrar(asamblea_id: uuid.UUID, body: CerrarIn, ctx: TenantCtx, db: DbSession) -> AsambleaDetalle:
    await s.cerrar(db, ctx, asamblea_id, body)
    await db.commit()
    return await _detalle(db, ctx, asamblea_id)


# --- Acta ------------------------------------------------------------------------------------------


@router.get("/{asamblea_id}/acta.pdf")
async def acta_pdf(asamblea_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> Response:
    a = await s.obtener(db, ctx, asamblea_id)
    pdf = await acta.generar_pdf(db, a)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="acta-{a.consecutivo:03d}.pdf"'},
    )


@router.post("/{asamblea_id}/acta/guardar", response_model=AsambleaDetalle)
async def guardar_acta(asamblea_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> AsambleaDetalle:
    """Guarda el acta en Documentos (categoría Actas): la procesan el buscador y el resumidor de actas."""
    a = await s.obtener(db, ctx, asamblea_id)
    pdf = await acta.generar_pdf(db, a)
    doc = await acta.guardar_en_documentos(db, ctx, a, pdf)
    await _enqueue_ingestion(db, ctx, doc)  # hace commit y encola la ingesta
    return await _detalle(db, ctx, asamblea_id)
