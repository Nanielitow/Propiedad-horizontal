"""API del panel de recaudos: dashboard, alertas, reportes exportables y cortes mensuales."""

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Path, Query, Response, status
from fastapi.concurrency import run_in_threadpool

from app.api.deps import DbSession, TenantCtx
from app.api.v1.recaudos import confirmar
from app.models.enums import EstadoAlerta
from app.schemas.recaudos import AtencionAlertaIn
from app.schemas.recaudos_out import AlertaOut, CorteOut, DashboardOut
from app.services.recaudos import alertas, consultas, cortes, exportar, reportes
from app.services.recaudos.dominio import TZ
from app.services.recaudos.reportes import TipoReporte

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


# --- Reportes ---------------------------------------------------------------------------

_MIME = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


@router.get("/reportes/{tipo}", response_model=None)
async def reporte(
    tipo: TipoReporte,
    ctx: TenantCtx,
    db: DbSession,
    desde: date | None = None,
    hasta: date | None = None,
    formato: Literal["json", "xlsx", "pdf"] = "json",
) -> dict[str, Any] | Response:
    """Informe del periodo (por defecto, el mes en curso) en pantalla, Excel o PDF."""
    if desde is None or hasta is None:
        desde, hasta = reportes.mes_actual()
    r = await reportes.generar_reporte(db, ctx, tipo, desde, hasta)
    if formato == "json":
        return exportar.a_json(r)
    # El PDF y el Excel se dibujan en un hilo: no bloquean a las demás peticiones
    datos = await run_in_threadpool(exportar.a_pdf if formato == "pdf" else exportar.a_excel, r)
    return Response(
        content=datos,
        media_type=_MIME[formato],
        headers={"Content-Disposition": f'attachment; filename="{r.nombre_archivo}.{formato}"'},
    )


@router.get("/cortes", response_model=list[CorteOut])
async def listar_cortes(ctx: TenantCtx, db: DbSession) -> list[CorteOut]:
    return [CorteOut.model_validate(c, from_attributes=True) for c in await cortes.listar_cortes(db, ctx)]


@router.post("/cortes/{anio}/{mes}", response_model=CorteOut, status_code=status.HTTP_201_CREATED)
async def generar_corte(
    anio: Annotated[int, Path(ge=2000, le=2100)], mes: Annotated[int, Path(ge=1, le=12)], ctx: TenantCtx, db: DbSession
) -> CorteOut:
    """Genera a mano el corte de un mes cerrado (normalmente lo hace la tarea del día 1)."""
    await cortes.generar_corte_manual(db, ctx, anio, mes)
    await confirmar(db, ctx)
    vistas = await cortes.listar_cortes(db, ctx)
    return CorteOut.model_validate(
        next(v for v in vistas if (v.periodo.year, v.periodo.month) == (anio, mes)), from_attributes=True
    )
