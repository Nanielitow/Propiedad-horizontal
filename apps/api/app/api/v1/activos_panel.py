"""API del panel del módulo de mantenimiento: indicadores y reportes exportables.

Se registra antes que app/api/v1/activos.py (/activos/{activo_id} capturaría /dashboard).
"""

import uuid
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Response
from fastapi.concurrency import run_in_threadpool

from app.api.deps import DbSession, TenantCtx
from app.services.activos import panel, reportes
from app.services.activos.reportes import TipoReporteActivos
from app.services.recaudos import exportar

router = APIRouter(prefix="/tenants/{tenant_id}/activos", tags=["activos: panel"])

MIME = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


@router.get("/dashboard", response_model=None)
async def dashboard(
    ctx: TenantCtx,
    db: DbSession,
    anio: Annotated[int | None, Query(ge=2000, le=2100)] = None,
    mes: Annotated[int | None, Query(ge=1, le=12)] = None,
    categoria_id: uuid.UUID | None = None,
    ubicacion: Annotated[str | None, Query(max_length=100)] = None,
) -> dict[str, Any]:
    """Indicadores del mes y del año (por defecto, los actuales). El Consejo recibe solo consolidados."""
    a, m = panel.anio_mes(anio, mes)
    return await panel.panel(db, ctx, a, m, categoria_id, ubicacion)


@router.get("/reportes/{tipo}", response_model=None)
async def reporte(
    tipo: TipoReporteActivos,
    ctx: TenantCtx,
    db: DbSession,
    desde: date | None = None,
    hasta: date | None = None,
    formato: Literal["json", "xlsx", "pdf"] = "json",
) -> dict[str, Any] | Response:
    """Informe en pantalla, Excel o PDF. Con periodo (por defecto, el año en curso): cumplimiento,
    correctivos y costos; los demás son un corte a hoy."""
    r = await reportes.generar(db, ctx, tipo, desde, hasta)
    if formato == "json":
        return exportar.a_json(r)
    datos = await run_in_threadpool(exportar.a_pdf if formato == "pdf" else exportar.a_excel, r)
    nombre = f"{tipo}-{r.hasta.isoformat()}" if r.corte else r.nombre_archivo
    return Response(
        content=datos,
        media_type=MIME[formato],
        headers={"Content-Disposition": f'attachment; filename="{nombre}.{formato}"'},
    )
