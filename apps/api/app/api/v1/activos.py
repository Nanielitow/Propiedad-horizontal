"""API del módulo de activos: buscador y hoja de vida de cada activo.

Las rutas con prefijo fijo (/planes, /novedades, /qr...) están en
activos_operacion.py, que se registra antes que este router.
"""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool

from app.api.deps import DbSession, TenantCtx
from app.api.v1.activos_operacion import limitar_escritura, tenant_slug_y_nombre
from app.api.v1.activos_panel import MIME
from app.models.enums import Criticidad, EstadoActivo
from app.schemas.activos import ActivoIn, ActivoUpdate, BajaIn, LecturaIn, VinculoDocumentoIn
from app.schemas.activos_out import ActivoDetalle, ActivosPagina, Color, LecturaOut
from app.services.activos import activos, consultas, qr, reportes
from app.services.activos.consultas import FiltroActivos
from app.services.recaudos import exportar

router = APIRouter(prefix="/tenants/{tenant_id}/activos", tags=["activos"])


async def _detalle(db: DbSession, ctx: TenantCtx, activo_id: uuid.UUID) -> ActivoDetalle:
    slug, _ = await tenant_slug_y_nombre(db, ctx)
    return await consultas.detalle_activo(db, ctx, activo_id, tenant_slug=slug)


@router.get("", response_model=ActivosPagina)
async def buscar_activos(
    ctx: TenantCtx,
    db: DbSession,
    categoria_id: uuid.UUID | None = None,
    ubicacion: Annotated[str | None, Query(max_length=100)] = None,
    estado: EstadoActivo | None = None,
    criticidad: Criticidad | None = None,
    semaforo: Color | None = None,
    texto: Annotated[str | None, Query(max_length=100)] = None,
    incluir_bajas: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> ActivosPagina:
    filtro = FiltroActivos(categoria_id, ubicacion, estado, criticidad, semaforo, texto, incluir_bajas)
    return await consultas.buscar_activos(db, ctx, filtro, page=page, page_size=page_size)


@router.post("", response_model=ActivoDetalle, status_code=status.HTTP_201_CREATED)
async def crear_activo(body: ActivoIn, request: Request, ctx: TenantCtx, db: DbSession) -> ActivoDetalle:
    await limitar_escritura(request, ctx)
    a = await activos.crear_activo(db, ctx, body)
    await db.commit()
    return await _detalle(db, ctx, a.id)


@router.get("/{activo_id}", response_model=ActivoDetalle)
async def hoja_de_vida(activo_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> ActivoDetalle:
    return await _detalle(db, ctx, activo_id)


@router.patch("/{activo_id}", response_model=ActivoDetalle)
async def editar_activo(activo_id: uuid.UUID, body: ActivoUpdate, ctx: TenantCtx, db: DbSession) -> ActivoDetalle:
    await activos.editar_activo(db, ctx, activo_id, body)
    await db.commit()
    return await _detalle(db, ctx, activo_id)


@router.post("/{activo_id}/baja", response_model=ActivoDetalle)
async def dar_de_baja(activo_id: uuid.UUID, body: BajaIn, ctx: TenantCtx, db: DbSession) -> ActivoDetalle:
    """Reemplaza al borrado: el activo y su historial se conservan."""
    await activos.dar_de_baja(db, ctx, activo_id, body)
    await db.commit()
    return await _detalle(db, ctx, activo_id)


@router.get("/{activo_id}/qr.svg")
async def qr_svg(activo_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> Response:
    a = await activos.obtener(db, ctx, activo_id)
    slug, _ = await tenant_slug_y_nombre(db, ctx)
    return Response(
        content=qr.svg(qr.url_qr(slug, a.qr_token)),
        media_type="image/svg+xml",
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.post("/{activo_id}/qr/regenerar", response_model=ActivoDetalle)
async def regenerar_qr(activo_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> ActivoDetalle:
    """Para una etiqueta perdida o dañada: el QR anterior deja de funcionar."""
    await activos.regenerar_qr(db, ctx, activo_id)
    await db.commit()
    return await _detalle(db, ctx, activo_id)


@router.post("/{activo_id}/documentos", response_model=ActivoDetalle, status_code=status.HTTP_201_CREATED)
async def vincular_documento(
    activo_id: uuid.UUID, body: VinculoDocumentoIn, ctx: TenantCtx, db: DbSession
) -> ActivoDetalle:
    await activos.vincular_documento(db, ctx, activo_id, body)
    await db.commit()
    return await _detalle(db, ctx, activo_id)


@router.delete("/{activo_id}/documentos/{document_id}", response_model=ActivoDetalle)
async def desvincular_documento(
    activo_id: uuid.UUID, document_id: uuid.UUID, ctx: TenantCtx, db: DbSession
) -> ActivoDetalle:
    """Quita el vínculo; el documento sigue en el archivo de la copropiedad."""
    await activos.desvincular_documento(db, ctx, activo_id, document_id)
    await db.commit()
    return await _detalle(db, ctx, activo_id)


@router.get("/{activo_id}/lecturas", response_model=list[LecturaOut])
async def lecturas(activo_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> list[LecturaOut]:
    return await consultas.lecturas(db, ctx, activo_id)


@router.post("/{activo_id}/lecturas", response_model=LecturaOut, status_code=status.HTTP_201_CREATED)
async def registrar_lectura(
    activo_id: uuid.UUID, body: LecturaIn, request: Request, ctx: TenantCtx, db: DbSession
) -> LecturaOut:
    await limitar_escritura(request, ctx)
    lectura = await activos.registrar_lectura(db, ctx, activo_id, body)
    await db.commit()
    return LecturaOut.model_validate(lectura)


@router.get("/{activo_id}/dossier.{formato}")
async def dossier(activo_id: uuid.UUID, formato: Literal["pdf", "xlsx"], ctx: TenantCtx, db: DbSession) -> Response:
    """Hoja de vida individual completa (ficha, planes, historial, fallas, recomendaciones, costos y QR)."""
    r, qr_url = await reportes.dossier(db, ctx, activo_id)
    if formato == "pdf":
        datos = await run_in_threadpool(reportes.dossier_pdf, r, qr_url)
    else:
        datos = await run_in_threadpool(exportar.a_excel, r)
    codigo = r.titulo.split(" · ")[1].split(" ")[0]
    return Response(
        content=datos,
        media_type=MIME[formato],
        headers={"Content-Disposition": f'attachment; filename="hoja-de-vida-{codigo}.{formato}"'},
    )
