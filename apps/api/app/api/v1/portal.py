"""API del portal del residente: PQRS, circulares, reservas e inicio (docs/PORTAL.md).

Los avisos por correo se encolan DESPUÉS del commit (si la transacción falla, no se avisa nada).
"""

import uuid
from datetime import date, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, status
from fastapi.concurrency import run_in_threadpool

from app.api.deps import DbSession, TenantCtx
from app.core.rate_limit import DEMO_PORTAL_PER_IP_DAY, PORTAL_WRITES_PER_MINUTE, enforce, enforce_demo
from app.models.enums import CategoriaPqrs, EstadoPqrs, EstadoReserva, UserRole
from app.schemas.portal import (
    AdjuntoUploadIn,
    CalificacionIn,
    CancelarReservaIn,
    CircularIn,
    CircularUpdate,
    DecisionReservaIn,
    GestionPqrsIn,
    MensajeIn,
    NovedadDesdePqrsIn,
    PqrsIn,
    ReabrirIn,
    ReglasZonaIn,
    ReservaPortalIn,
    RespuestaIn,
)
from app.schemas.portal_out import (
    CircularOut,
    InicioResidente,
    OcupadoOut,
    PendientesPersonal,
    PqrsDetalle,
    PqrsResumen,
    PqrsResumenBandeja,
    ReservaOut,
    ZonaOut,
)
from app.services.comun import ValidacionError, exigir, hoy_bogota
from app.services.portal import adjuntos, circulares, consultas, pqrs, reservas
from app.services.portal import dominio as d
from app.services.portal.consultas import FiltroPqrs
from app.workers.celery_app import celery_app

router = APIRouter(prefix="/tenants/{tenant_id}/portal", tags=["portal del residente"])


async def limitar(request: Request, ctx: TenantCtx) -> None:
    await enforce(request, PORTAL_WRITES_PER_MINUTE, str(ctx.user_id))
    await enforce_demo(request, DEMO_PORTAL_PER_IP_DAY, demo=ctx.is_demo)


async def _encolar(nombre: str, *args: str) -> None:
    await run_in_threadpool(celery_app.send_task, nombre, args=list(args))


# --- Inicio ----------------------------------------------------------------------------------


@router.get("/inicio", response_model=InicioResidente)
async def inicio(ctx: TenantCtx, db: DbSession) -> InicioResidente:
    if ctx.role != UserRole.RESIDENTE:
        raise ValidacionError("El inicio del portal es para residentes")
    return await consultas.inicio_residente(db, ctx)


@router.get("/pendientes", response_model=PendientesPersonal)
async def pendientes(ctx: TenantCtx, db: DbSession) -> PendientesPersonal:
    exigir(ctx, d.PUEDE_VER_PQRS, "ver los pendientes del portal")
    return await consultas.pendientes_personal(db, ctx)


# --- Adjuntos --------------------------------------------------------------------------------


@router.post("/adjuntos/upload-url", response_model=None)
async def url_subida(body: AdjuntoUploadIn, request: Request, ctx: TenantCtx) -> dict[str, Any]:
    await limitar(request, ctx)
    s = adjuntos.url_subida(ctx, body.content_type, body.size_bytes)
    return {"storage_key": s.storage_key, "upload_url": s.upload_url, "headers": s.headers, "expires_in": s.expires_in}


# --- PQRS -------------------------------------------------------------------------------------


@router.get("/pqrs", response_model=list[PqrsResumen])
async def listar_pqrs(
    ctx: TenantCtx,
    db: DbSession,
    estado: EstadoPqrs | None = None,
    categoria: CategoriaPqrs | None = None,
    solo_abiertas: bool = False,
    vencidas: bool = False,
    asignadas_a_mi: bool = False,
    sin_asignar: bool = False,
    texto: Annotated[str | None, Query(max_length=100)] = None,
) -> list[PqrsResumen]:
    f = FiltroPqrs(estado, categoria, solo_abiertas, vencidas, asignadas_a_mi, sin_asignar, texto)
    return await consultas.listar_pqrs(db, ctx, f)


@router.get("/pqrs/resumen", response_model=PqrsResumenBandeja)
async def resumen_pqrs(ctx: TenantCtx, db: DbSession) -> PqrsResumenBandeja:
    exigir(ctx, d.PUEDE_VER_PQRS, "ver el resumen de PQRS")
    return await consultas.resumen_bandeja(db, ctx)


@router.post("/pqrs", response_model=PqrsDetalle, status_code=status.HTTP_201_CREATED)
async def radicar(body: PqrsIn, request: Request, ctx: TenantCtx, db: DbSession) -> PqrsDetalle:
    await limitar(request, ctx)
    p = await pqrs.radicar(db, ctx, body)
    await db.commit()
    await _encolar("portal.pqrs_radicada", str(ctx.tenant_id), str(p.id))
    return await consultas.detalle_pqrs(db, ctx, p.id)


@router.get("/pqrs/{pqrs_id}", response_model=PqrsDetalle)
async def detalle(pqrs_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> PqrsDetalle:
    return await consultas.detalle_pqrs(db, ctx, pqrs_id)


@router.post("/pqrs/{pqrs_id}/mensajes", response_model=PqrsDetalle)
async def comentar(pqrs_id: uuid.UUID, body: MensajeIn, request: Request, ctx: TenantCtx, db: DbSession) -> PqrsDetalle:
    await limitar(request, ctx)
    await pqrs.comentar(db, ctx, pqrs_id, body)
    await db.commit()
    return await consultas.detalle_pqrs(db, ctx, pqrs_id)


@router.post("/pqrs/{pqrs_id}/responder", response_model=PqrsDetalle)
async def responder(
    pqrs_id: uuid.UUID, body: RespuestaIn, request: Request, ctx: TenantCtx, db: DbSession
) -> PqrsDetalle:
    await limitar(request, ctx)
    await pqrs.responder(db, ctx, pqrs_id, body)
    await db.commit()
    await _encolar("portal.pqrs_respondida", str(ctx.tenant_id), str(pqrs_id), body.texto)
    return await consultas.detalle_pqrs(db, ctx, pqrs_id)


@router.patch("/pqrs/{pqrs_id}", response_model=PqrsDetalle)
async def gestionar(
    pqrs_id: uuid.UUID, body: GestionPqrsIn, request: Request, ctx: TenantCtx, db: DbSession
) -> PqrsDetalle:
    await limitar(request, ctx)
    await pqrs.gestionar(db, ctx, pqrs_id, body)
    await db.commit()
    return await consultas.detalle_pqrs(db, ctx, pqrs_id)


@router.post("/pqrs/{pqrs_id}/calificar", response_model=PqrsDetalle)
async def calificar(
    pqrs_id: uuid.UUID, body: CalificacionIn, request: Request, ctx: TenantCtx, db: DbSession
) -> PqrsDetalle:
    await limitar(request, ctx)
    await pqrs.calificar(db, ctx, pqrs_id, body)
    await db.commit()
    return await consultas.detalle_pqrs(db, ctx, pqrs_id)


@router.post("/pqrs/{pqrs_id}/reabrir", response_model=PqrsDetalle)
async def reabrir(pqrs_id: uuid.UUID, body: ReabrirIn, request: Request, ctx: TenantCtx, db: DbSession) -> PqrsDetalle:
    await limitar(request, ctx)
    await pqrs.reabrir(db, ctx, pqrs_id, body)
    await db.commit()
    return await consultas.detalle_pqrs(db, ctx, pqrs_id)


@router.post("/pqrs/{pqrs_id}/desistir", response_model=PqrsDetalle)
async def desistir(pqrs_id: uuid.UUID, body: ReabrirIn, request: Request, ctx: TenantCtx, db: DbSession) -> PqrsDetalle:
    await limitar(request, ctx)
    await pqrs.desistir(db, ctx, pqrs_id, body.texto)
    await db.commit()
    return await consultas.detalle_pqrs(db, ctx, pqrs_id)


@router.post("/pqrs/{pqrs_id}/novedad", response_model=PqrsDetalle)
async def convertir_en_novedad(
    pqrs_id: uuid.UUID, body: NovedadDesdePqrsIn, request: Request, ctx: TenantCtx, db: DbSession
) -> PqrsDetalle:
    await limitar(request, ctx)
    await pqrs.convertir_en_novedad(db, ctx, pqrs_id, body)
    await db.commit()
    return await consultas.detalle_pqrs(db, ctx, pqrs_id)


# --- Circulares -------------------------------------------------------------------------------


@router.get("/circulares", response_model=list[CircularOut])
async def listar_circulares(ctx: TenantCtx, db: DbSession, incluir_archivadas: bool = False) -> list[CircularOut]:
    return await consultas.listar_circulares(db, ctx, incluir_archivadas=incluir_archivadas)


@router.post("/circulares", response_model=CircularOut, status_code=status.HTTP_201_CREATED)
async def crear_circular(body: CircularIn, request: Request, ctx: TenantCtx, db: DbSession) -> CircularOut:
    await limitar(request, ctx)
    c = await circulares.crear(db, ctx, body)
    await db.commit()
    return await consultas.circular(db, ctx, c.id)


@router.get("/circulares/{circular_id}", response_model=CircularOut)
async def ver_circular(circular_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> CircularOut:
    return await consultas.circular(db, ctx, circular_id)


@router.patch("/circulares/{circular_id}", response_model=CircularOut)
async def editar_circular(
    circular_id: uuid.UUID, body: CircularUpdate, request: Request, ctx: TenantCtx, db: DbSession
) -> CircularOut:
    await limitar(request, ctx)
    await circulares.editar(db, ctx, circular_id, body)
    await db.commit()
    return await consultas.circular(db, ctx, circular_id)


@router.post("/circulares/{circular_id}/publicar", response_model=CircularOut)
async def publicar(circular_id: uuid.UUID, request: Request, ctx: TenantCtx, db: DbSession) -> CircularOut:
    await limitar(request, ctx)
    c = await circulares.publicar(db, ctx, circular_id)
    await db.commit()
    if c.enviar_correo:
        await _encolar("portal.circular_publicada", str(ctx.tenant_id), str(c.id))
    return await consultas.circular(db, ctx, circular_id)


@router.post("/circulares/{circular_id}/archivar", response_model=CircularOut)
async def archivar(circular_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> CircularOut:
    await circulares.archivar(db, ctx, circular_id)
    await db.commit()
    return await consultas.circular(db, ctx, circular_id)


@router.post("/circulares/{circular_id}/leida", status_code=status.HTTP_204_NO_CONTENT)
async def marcar_leida(circular_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> None:
    await circulares.marcar_leida(db, ctx, circular_id)
    await db.commit()


# --- Zonas y reservas --------------------------------------------------------------------------


@router.get("/zonas", response_model=list[ZonaOut])
async def zonas(ctx: TenantCtx, db: DbSession) -> list[ZonaOut]:
    return await consultas.zonas(db, ctx)


@router.patch("/zonas/{zona_id}", response_model=ZonaOut)
async def configurar_zona(zona_id: uuid.UUID, body: ReglasZonaIn, ctx: TenantCtx, db: DbSession) -> ZonaOut:
    z = await reservas.configurar_zona(db, ctx, zona_id, body)
    await db.commit()
    await db.refresh(z)
    return consultas.zona_out(z)


@router.get("/zonas/{zona_id}/disponibilidad", response_model=list[OcupadoOut])
async def disponibilidad(
    zona_id: uuid.UUID, ctx: TenantCtx, db: DbSession, desde: date | None = None, hasta: date | None = None
) -> list[OcupadoOut]:
    desde = desde or hoy_bogota()
    hasta = hasta or desde + timedelta(days=60)
    return [OcupadoOut(**o.__dict__) for o in await reservas.disponibilidad(db, ctx, zona_id, desde, hasta)]


@router.get("/reservas", response_model=list[ReservaOut])
async def listar_reservas(
    ctx: TenantCtx,
    db: DbSession,
    estado: EstadoReserva | None = None,
    desde: date | None = None,
    hasta: date | None = None,
) -> list[ReservaOut]:
    return await consultas.reservas_out(db, await reservas.listar(db, ctx, estado=estado, desde=desde, hasta=hasta))


@router.post("/reservas", response_model=ReservaOut, status_code=status.HTTP_201_CREATED)
async def solicitar(body: ReservaPortalIn, request: Request, ctx: TenantCtx, db: DbSession) -> ReservaOut:
    await limitar(request, ctx)
    r = await reservas.solicitar(db, ctx, body)
    await db.commit()
    if r.estado == EstadoReserva.SOLICITADA:
        await _encolar("portal.reserva_solicitada", str(ctx.tenant_id), str(r.id))
    return (await consultas.reservas_out(db, [r]))[0]


@router.post("/reservas/{reserva_id}/cancelar", response_model=ReservaOut)
async def cancelar(
    reserva_id: uuid.UUID, body: CancelarReservaIn, request: Request, ctx: TenantCtx, db: DbSession
) -> ReservaOut:
    await limitar(request, ctx)
    r = await reservas.cancelar(db, ctx, reserva_id, body)
    await db.commit()
    return (await consultas.reservas_out(db, [r]))[0]


@router.post("/reservas/{reserva_id}/decidir", response_model=ReservaOut)
async def decidir(
    reserva_id: uuid.UUID, body: DecisionReservaIn, request: Request, ctx: TenantCtx, db: DbSession
) -> ReservaOut:
    await limitar(request, ctx)
    r = await reservas.decidir(db, ctx, reserva_id, body)
    await db.commit()
    await _encolar("portal.reserva_decidida", str(ctx.tenant_id), str(r.id))
    return (await consultas.reservas_out(db, [r]))[0]
