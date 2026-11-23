"""API del panel de recaudos: dashboard ejecutivo y alertas de auditoría."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession, TenantCtx
from app.api.v1.recaudos import confirmar
from app.models.enums import EstadoAlerta
from app.schemas.recaudos import AtencionAlertaIn
from app.schemas.recaudos_out import AlertaOut, DashboardOut
from app.services.recaudos import alertas, consultas
from app.services.recaudos.dominio import TZ

router = APIRouter(prefix="/tenants/{tenant_id}/recaudos", tags=["recaudos: panel"])


@router.get("/dashboard", response_model=DashboardOut)
async def dashboard(
    ctx: TenantCtx,
    db: DbSession,
    anio: Annotated[int | None, Query(ge=2000, le=2100)] = None,
    mes: Annotated[int | None, Query(ge=1, le=12)] = None,
) -> DashboardOut:
    """Por defecto, el mes en curso (hora de Bogotá)."""
    hoy = datetime.now(TZ)
    return await consultas.dashboard(db, ctx, anio or hoy.year, mes or hoy.month)


@router.get("/alertas", response_model=list[AlertaOut])
async def listar_alertas(
    ctx: TenantCtx, db: DbSession, estado: EstadoAlerta | None = EstadoAlerta.ABIERTA, todas: bool = False
) -> list[AlertaOut]:
    lista = await alertas.listar_alertas(db, ctx, None if todas else estado)
    return [AlertaOut.model_validate(a) for a in lista]


@router.post("/alertas/{alerta_id}/atender", response_model=AlertaOut)
async def atender_alerta(alerta_id: uuid.UUID, body: AtencionAlertaIn, ctx: TenantCtx, db: DbSession) -> AlertaOut:
    alerta = await alertas.atender_alerta(db, ctx, alerta_id, body.resolucion)
    await confirmar(db, ctx)
    return AlertaOut.model_validate(alerta)
