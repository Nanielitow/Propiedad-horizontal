"""API de control de efectivo y conciliación: caja, entregas internas y consignaciones."""

import uuid

from fastapi import APIRouter, Request, status

from app.api.deps import DbSession, TenantCtx
from app.api.v1.recaudos import confirmar, limitar_escritura
from app.models.enums import EstadoConsignacion, EstadoEntrega
from app.schemas.recaudos import CierreCajaIn, ConsignacionCreate, EntregaConfirmacion, EntregaCreate, RechazoIn
from app.schemas.recaudos_out import (
    CierreDetalle,
    CierreOut,
    ConsignacionDetalle,
    ConsignacionOut,
    EntregaDetalle,
    EntregaOut,
    PendienteOut,
    ResultadoConsignacion,
    ResumenCajaOut,
)
from app.services.recaudos import caja, conciliacion, consultas

router = APIRouter(prefix="/tenants/{tenant_id}/recaudos", tags=["recaudos: caja y conciliación"])


# --- Caja -----------------------------------------------------------------------------


@router.get("/caja/estado", response_model=ResumenCajaOut)
async def estado_caja(ctx: TenantCtx, db: DbSession) -> ResumenCajaOut:
    """Vista previa del cierre: el efectivo que el sistema espera en la caja del usuario."""
    resumen = await caja.estado_caja(db, ctx)
    return ResumenCajaOut(
        inicio_turno=resumen.inicio_turno,
        cantidad=resumen.cantidad,
        total_efectivo=resumen.total_efectivo,
        recaudos=await consultas.filas_por_ids(db, [r.id for r in resumen.recaudos]),
    )


@router.post("/caja/cierres", response_model=CierreDetalle, status_code=status.HTTP_201_CREATED)
async def cerrar_caja(body: CierreCajaIn, request: Request, ctx: TenantCtx, db: DbSession) -> CierreDetalle:
    await limitar_escritura(request, ctx)
    cierre, alertas = await caja.cerrar_caja(db, ctx, body)
    await confirmar(db, ctx, alertas)
    return await consultas.detalle_cierre(db, ctx, cierre.id)


@router.get("/caja/cierres", response_model=list[CierreOut])
async def listar_cierres(ctx: TenantCtx, db: DbSession, usuario_id: uuid.UUID | None = None) -> list[CierreOut]:
    return await consultas.listar_cierres(db, ctx, usuario_id=usuario_id)


@router.get("/caja/cierres/{cierre_id}", response_model=CierreDetalle)
async def detalle_cierre(cierre_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> CierreDetalle:
    return await consultas.detalle_cierre(db, ctx, cierre_id)


# --- Entregas internas -------------------------------------------------------------


@router.get("/entregas", response_model=list[EntregaOut])
async def listar_entregas(
    ctx: TenantCtx, db: DbSession, estado: EstadoEntrega | None = None, para_mi: bool = False
) -> list[EntregaOut]:
    return await consultas.listar_entregas(db, ctx, estado=estado, para_mi=para_mi)


@router.post("/entregas", response_model=EntregaDetalle, status_code=status.HTTP_201_CREATED)
async def crear_entrega(body: EntregaCreate, request: Request, ctx: TenantCtx, db: DbSession) -> EntregaDetalle:
    await limitar_escritura(request, ctx)
    entrega = await caja.crear_entrega(db, ctx, body)
    await confirmar(db, ctx)
    return await consultas.detalle_entrega(db, ctx, entrega.id)


@router.get("/entregas/{entrega_id}", response_model=EntregaDetalle)
async def detalle_entrega(entrega_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> EntregaDetalle:
    return await consultas.detalle_entrega(db, ctx, entrega_id)


@router.post("/entregas/{entrega_id}/confirmar", response_model=EntregaDetalle)
async def confirmar_entrega(
    entrega_id: uuid.UUID, body: EntregaConfirmacion, ctx: TenantCtx, db: DbSession
) -> EntregaDetalle:
    _, alertas = await caja.confirmar_entrega(db, ctx, entrega_id, body)
    await confirmar(db, ctx, alertas)
    return await consultas.detalle_entrega(db, ctx, entrega_id)


@router.post("/entregas/{entrega_id}/rechazar", response_model=EntregaDetalle)
async def rechazar_entrega(entrega_id: uuid.UUID, body: RechazoIn, ctx: TenantCtx, db: DbSession) -> EntregaDetalle:
    await caja.rechazar_entrega(db, ctx, entrega_id, body.motivo)
    await confirmar(db, ctx)
    return await consultas.detalle_entrega(db, ctx, entrega_id)


# --- Consignaciones ----------------------------------------------------------------


@router.get("/consignaciones/pendientes", response_model=list[PendienteOut])
async def efectivo_por_consignar(ctx: TenantCtx, db: DbSession) -> list[PendienteOut]:
    pendientes = await conciliacion.pendientes_por_consignar(db, ctx)
    filas = {f.id: f for f in await consultas.filas_por_ids(db, [p.recaudo.id for p in pendientes])}
    return [PendienteOut(recaudo=filas[p.recaudo.id], saldo=p.saldo) for p in pendientes]


@router.get("/consignaciones", response_model=list[ConsignacionOut])
async def listar_consignaciones(
    ctx: TenantCtx, db: DbSession, estado: EstadoConsignacion | None = None
) -> list[ConsignacionOut]:
    return await consultas.listar_consignaciones(db, ctx, estado=estado)


@router.post("/consignaciones", response_model=ConsignacionDetalle, status_code=status.HTTP_201_CREATED)
async def registrar_consignacion(
    body: ConsignacionCreate, request: Request, ctx: TenantCtx, db: DbSession
) -> ConsignacionDetalle:
    await limitar_escritura(request, ctx)
    c, alertas = await conciliacion.registrar_consignacion(db, ctx, body)
    await confirmar(db, ctx, alertas)
    return await consultas.detalle_consignacion(db, ctx, c.id)


@router.get("/consignaciones/{consignacion_id}", response_model=ConsignacionDetalle)
async def detalle_consignacion(consignacion_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> ConsignacionDetalle:
    return await consultas.detalle_consignacion(db, ctx, consignacion_id)


@router.post("/consignaciones/{consignacion_id}/aprobar", response_model=ResultadoConsignacion)
async def aprobar_consignacion(consignacion_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> ResultadoConsignacion:
    c, recaudos = await conciliacion.aprobar_consignacion(db, ctx, consignacion_id)
    await confirmar(db, ctx)
    return ResultadoConsignacion(
        consignacion=await consultas.consignacion_out(db, c), recaudos_actualizados=[r.id for r in recaudos]
    )


@router.post("/consignaciones/{consignacion_id}/verificar", response_model=ResultadoConsignacion)
async def verificar_consignacion(consignacion_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> ResultadoConsignacion:
    c, recaudos = await conciliacion.verificar_consignacion(db, ctx, consignacion_id)
    await confirmar(db, ctx)
    return ResultadoConsignacion(
        consignacion=await consultas.consignacion_out(db, c), recaudos_actualizados=[r.id for r in recaudos]
    )


@router.post("/consignaciones/{consignacion_id}/rechazar", response_model=ConsignacionOut)
async def rechazar_consignacion(
    consignacion_id: uuid.UUID, body: RechazoIn, ctx: TenantCtx, db: DbSession
) -> ConsignacionOut:
    c = await conciliacion.rechazar_consignacion(db, ctx, consignacion_id, body.motivo)
    await confirmar(db, ctx)
    return await consultas.consignacion_out(db, c)
