"""API del módulo de activos: rutas con prefijo fijo (catálogos, QR, evidencias,
planes, actividades, mantenimientos, novedades, recomendaciones y auditoría).

Va ANTES que app/api/v1/activos.py en el router: /activos/{activo_id} capturaría
estos segmentos. Los permisos los aplica el servicio (y RLS debajo); cada endpoint
que escribe hace commit y, si corresponde, encola el correo DESPUÉS.
"""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Path, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select

from app.api.deps import DbSession, TenantCtx
from app.core.rate_limit import ACTIVOS_WRITES_PER_MINUTE, DEMO_ACTIVOS_PER_IP_DAY, enforce, enforce_demo
from app.models import Activo, Tenant
from app.models.enums import (
    EntidadEvidencia,
    EstadoActividad,
    EstadoActivo,
    EstadoNovedad,
    EstadoRecomendacion,
    PrioridadNovedad,
    PrioridadRecomendacion,
    TipoMantenimiento,
)
from app.schemas.activos import (
    AnulacionIn,
    AsignacionIn,
    ContratistaIn,
    ContratistaUpdate,
    EvidenciaIn,
    EvidenciaUploadIn,
    MantenimientoIn,
    MotivoIn,
    NovedadAvance,
    NovedadIn,
    PlanIn,
    PlanUpdate,
    RecomendacionIn,
    RecomendacionUpdate,
    ReprogramacionIn,
)
from app.schemas.activos_out import (
    ActividadOut,
    AuditoriaOut,
    CategoriaOut,
    Color,
    ContratistaDetalle,
    ContratistaOut,
    EvidenciaOut,
    EvidenciaUploadOut,
    MantenimientoDetalle,
    MantenimientoResumen,
    NovedadOut,
    PersonaOut,
    PlanOut,
    QrResuelto,
    RecomendacionOut,
    ReprogramacionOut,
)
from app.services.activos import (
    catalogo,
    consultas,
    evidencias,
    mantenimientos,
    novedades,
    planes,
    qr,
    recomendaciones,
)
from app.services.activos.consultas import FiltroActividades
from app.services.activos.dominio import PUEDE_VER
from app.services.comun import ValidacionError, exigir
from app.workers.celery_app import celery_app

router = APIRouter(prefix="/tenants/{tenant_id}/activos", tags=["activos"])

NOVEDAD_CRITICA_TASK = "activos.novedad_critica"
MAX_ETIQUETAS = 200


async def limitar_escritura(request: Request, ctx: TenantCtx) -> None:
    await enforce(request, ACTIVOS_WRITES_PER_MINUTE, str(ctx.user_id))
    await enforce_demo(request, DEMO_ACTIVOS_PER_IP_DAY)


async def tenant_slug_y_nombre(db: DbSession, ctx: TenantCtx) -> tuple[str, str]:
    fila = (await db.execute(select(Tenant.slug, Tenant.name).where(Tenant.id == ctx.tenant_id))).one()
    return fila[0], fila[1]


# --- Catálogos ------------------------------------------------------------------------------


@router.get("/categorias", response_model=list[CategoriaOut])
async def listar_categorias(ctx: TenantCtx, db: DbSession) -> list[CategoriaOut]:
    return [CategoriaOut.model_validate(c) for c in await catalogo.listar_categorias(db, ctx)]


@router.get("/contratistas", response_model=list[ContratistaOut])
async def listar_contratistas(ctx: TenantCtx, db: DbSession, incluir_inactivos: bool = False) -> list[ContratistaOut]:
    lista = await catalogo.listar_contratistas(db, ctx, incluir_inactivos=incluir_inactivos)
    return [consultas.contratista_out(ctx, c) for c in lista]


@router.post("/contratistas", response_model=ContratistaOut, status_code=status.HTTP_201_CREATED)
async def crear_contratista(body: ContratistaIn, request: Request, ctx: TenantCtx, db: DbSession) -> ContratistaOut:
    await limitar_escritura(request, ctx)
    c = await catalogo.crear_contratista(db, ctx, body)
    await db.commit()
    return consultas.contratista_out(ctx, c)


@router.get("/contratistas/{contratista_id}", response_model=ContratistaDetalle)
async def detalle_contratista(contratista_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> ContratistaDetalle:
    return await consultas.contratista_detalle(db, ctx, contratista_id)


@router.patch("/contratistas/{contratista_id}", response_model=ContratistaOut)
async def editar_contratista(
    contratista_id: uuid.UUID, body: ContratistaUpdate, ctx: TenantCtx, db: DbSession
) -> ContratistaOut:
    c = await catalogo.editar_contratista(db, ctx, contratista_id, body)
    await db.commit()
    return consultas.contratista_out(ctx, c)


@router.get("/personal", response_model=list[PersonaOut])
async def listar_personal(ctx: TenantCtx, db: DbSession) -> list[PersonaOut]:
    return await consultas.personal(db, ctx)


# --- QR -----------------------------------------------------------------------------------------


@router.get("/etiquetas.pdf")
async def etiquetas(ctx: TenantCtx, db: DbSession, ids: Annotated[list[uuid.UUID] | None, Query()] = None) -> Response:
    """Hoja de etiquetas imprimible. Sin `ids`: todos los activos vigentes."""
    exigir(ctx, PUEDE_VER, "imprimir etiquetas")
    q = select(Activo).where(Activo.estado != EstadoActivo.DADO_DE_BAJA).order_by(Activo.consecutivo)
    if ids:
        q = q.where(Activo.id.in_(ids))
    lista = list(await db.scalars(q.limit(MAX_ETIQUETAS + 1)))
    if not lista:
        raise ValidacionError("No hay activos para imprimir")
    if len(lista) > MAX_ETIQUETAS:
        raise ValidacionError(f"Imprima máximo {MAX_ETIQUETAS} etiquetas a la vez")
    slug, nombre = await tenant_slug_y_nombre(db, ctx)
    pdf = await run_in_threadpool(qr.etiquetas_pdf, lista, slug, nombre)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="etiquetas-qr.pdf"'},
    )


@router.get("/qr/{token}", response_model=QrResuelto)
async def resolver_qr(token: Annotated[str, Path(max_length=64)], ctx: TenantCtx, db: DbSession) -> QrResuelto:
    """Vista rápida al escanear la etiqueta (requiere sesión; lo visible depende del rol)."""
    return await consultas.resolver_qr(db, ctx, token)


# --- Evidencias ------------------------------------------------------------------------------


@router.post("/evidencias/upload-url", response_model=EvidenciaUploadOut)
async def url_subida_evidencia(body: EvidenciaUploadIn, request: Request, ctx: TenantCtx) -> EvidenciaUploadOut:
    await limitar_escritura(request, ctx)
    s = evidencias.url_subida(ctx, body.content_type, body.size_bytes)
    return EvidenciaUploadOut(
        storage_key=s.storage_key, upload_url=s.upload_url, headers=s.headers, expires_in=s.expires_in
    )


@router.post("/evidencias", response_model=EvidenciaOut, status_code=status.HTTP_201_CREATED)
async def registrar_evidencia(body: EvidenciaIn, request: Request, ctx: TenantCtx, db: DbSession) -> EvidenciaOut:
    await limitar_escritura(request, ctx)
    ev = await evidencias.registrar(db, ctx, body)
    await db.commit()
    [registrada] = [
        e for e in await consultas.listar_evidencias(db, ctx, body.entidad, body.entidad_id) if e.id == ev.id
    ]
    return registrada


@router.get("/evidencias", response_model=list[EvidenciaOut])
async def listar_evidencias(
    entidad: EntidadEvidencia, entidad_id: uuid.UUID, ctx: TenantCtx, db: DbSession
) -> list[EvidenciaOut]:
    return await consultas.listar_evidencias(db, ctx, entidad, entidad_id)


# --- Planes ----------------------------------------------------------------------------------------


@router.get("/planes", response_model=list[PlanOut])
async def listar_planes(
    ctx: TenantCtx, db: DbSession, activo_id: uuid.UUID | None = None, pendientes_aprobacion: bool = False
) -> list[PlanOut]:
    return await consultas.listar_planes(db, ctx, activo_id=activo_id, pendientes_aprobacion=pendientes_aprobacion)


@router.post("/planes", response_model=PlanOut, status_code=status.HTTP_201_CREATED)
async def crear_plan(body: PlanIn, request: Request, ctx: TenantCtx, db: DbSession) -> PlanOut:
    await limitar_escritura(request, ctx)
    p = await planes.crear_plan(db, ctx, body)
    await db.commit()
    return await consultas.plan(db, ctx, p.id)


@router.get("/planes/{plan_id}", response_model=PlanOut)
async def detalle_plan(plan_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> PlanOut:
    return await consultas.plan(db, ctx, plan_id)


@router.patch("/planes/{plan_id}", response_model=PlanOut)
async def editar_plan(plan_id: uuid.UUID, body: PlanUpdate, ctx: TenantCtx, db: DbSession) -> PlanOut:
    await planes.editar_plan(db, ctx, plan_id, body)
    await db.commit()
    return await consultas.plan(db, ctx, plan_id)


@router.post("/planes/{plan_id}/aprobar", response_model=PlanOut)
async def aprobar_plan(plan_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> PlanOut:
    """Aprueba el plan y programa sus actividades de los próximos 12 meses."""
    await planes.aprobar_plan(db, ctx, plan_id)
    await db.commit()
    return await consultas.plan(db, ctx, plan_id)


@router.post("/planes/{plan_id}/pausar", response_model=PlanOut)
async def pausar_plan(plan_id: uuid.UUID, body: MotivoIn, ctx: TenantCtx, db: DbSession) -> PlanOut:
    """Pausa el plan y cancela sus actividades pendientes (quedan en el historial)."""
    await planes.pausar_plan(db, ctx, plan_id, body.motivo)
    await db.commit()
    return await consultas.plan(db, ctx, plan_id)


@router.post("/planes/{plan_id}/reanudar", response_model=PlanOut)
async def reanudar_plan(plan_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> PlanOut:
    await planes.reanudar_plan(db, ctx, plan_id)
    await db.commit()
    return await consultas.plan(db, ctx, plan_id)


# --- Actividades (calendario) ---------------------------------------------------------------


@router.get("/actividades", response_model=list[ActividadOut])
async def listar_actividades(
    ctx: TenantCtx,
    db: DbSession,
    desde: date | None = None,
    hasta: date | None = None,
    activo_id: uuid.UUID | None = None,
    plan_id: uuid.UUID | None = None,
    estado: EstadoActividad | None = None,
    semaforo: Color | None = None,
    asignado_a_id: uuid.UUID | None = None,
    mias: bool = False,
) -> list[ActividadOut]:
    if desde and hasta and (hasta - desde).days > 400:
        raise ValidacionError("Consulte máximo 400 días a la vez")
    filtro = FiltroActividades(desde, hasta, activo_id, plan_id, estado, semaforo, asignado_a_id, mias)
    return await consultas.listar_actividades(db, ctx, filtro)


@router.get("/actividades/{actividad_id}", response_model=ActividadOut)
async def detalle_actividad(actividad_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> ActividadOut:
    return await consultas.actividad(db, ctx, actividad_id)


@router.get("/actividades/{actividad_id}/reprogramaciones", response_model=list[ReprogramacionOut])
async def historial_reprogramaciones(actividad_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> list[ReprogramacionOut]:
    return await consultas.reprogramaciones(db, ctx, actividad_id)


@router.post("/actividades/{actividad_id}/reprogramar", response_model=ActividadOut)
async def reprogramar(actividad_id: uuid.UUID, body: ReprogramacionIn, ctx: TenantCtx, db: DbSession) -> ActividadOut:
    await planes.reprogramar(db, ctx, actividad_id, body)
    await db.commit()
    return await consultas.actividad(db, ctx, actividad_id)


@router.post("/actividades/{actividad_id}/asignar", response_model=ActividadOut)
async def asignar(actividad_id: uuid.UUID, body: AsignacionIn, ctx: TenantCtx, db: DbSession) -> ActividadOut:
    await planes.asignar(db, ctx, actividad_id, body.asignado_a_id)
    await db.commit()
    return await consultas.actividad(db, ctx, actividad_id)


# --- Mantenimientos ----------------------------------------------------------------------------------


@router.get("/mantenimientos", response_model=list[MantenimientoResumen])
async def listar_mantenimientos(
    ctx: TenantCtx,
    db: DbSession,
    activo_id: uuid.UUID | None = None,
    tipo: TipoMantenimiento | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    contratista_id: uuid.UUID | None = None,
    incluir_anulados: bool = True,
) -> list[MantenimientoResumen]:
    return await consultas.listar_mantenimientos(
        db,
        ctx,
        activo_id=activo_id,
        tipo=tipo,
        desde=desde,
        hasta=hasta,
        contratista_id=contratista_id,
        incluir_anulados=incluir_anulados,
    )


@router.post("/mantenimientos", response_model=MantenimientoDetalle, status_code=status.HTTP_201_CREATED)
async def registrar_mantenimiento(
    body: MantenimientoIn, request: Request, ctx: TenantCtx, db: DbSession
) -> MantenimientoDetalle:
    await limitar_escritura(request, ctx)
    m, _ = await mantenimientos.registrar(db, ctx, body)
    await db.commit()
    return await consultas.detalle_mantenimiento(db, ctx, m.id)


@router.get("/mantenimientos/{mantenimiento_id}", response_model=MantenimientoDetalle)
async def detalle_mantenimiento(mantenimiento_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> MantenimientoDetalle:
    return await consultas.detalle_mantenimiento(db, ctx, mantenimiento_id)


@router.post("/mantenimientos/{mantenimiento_id}/anular", response_model=MantenimientoDetalle)
async def anular_mantenimiento(
    mantenimiento_id: uuid.UUID, body: AnulacionIn, ctx: TenantCtx, db: DbSession
) -> MantenimientoDetalle:
    await mantenimientos.anular(db, ctx, mantenimiento_id, body.motivo)
    await db.commit()
    return await consultas.detalle_mantenimiento(db, ctx, mantenimiento_id)


# --- Novedades -----------------------------------------------------------------------------------------


@router.get("/novedades", response_model=list[NovedadOut])
async def listar_novedades(
    ctx: TenantCtx,
    db: DbSession,
    estado: Annotated[list[EstadoNovedad] | None, Query()] = None,
    abiertas: bool = False,
    prioridad: PrioridadNovedad | None = None,
    activo_id: uuid.UUID | None = None,
    mias: bool = False,
) -> list[NovedadOut]:
    return await consultas.listar_novedades(
        db, ctx, estados=estado, abiertas=abiertas, prioridad=prioridad, activo_id=activo_id, mias=mias
    )


@router.post("/novedades", response_model=NovedadOut, status_code=status.HTTP_201_CREATED)
async def reportar_novedad(body: NovedadIn, request: Request, ctx: TenantCtx, db: DbSession) -> NovedadOut:
    """Reporta una falla. Si es crítica, la administración recibe un correo inmediato."""
    await limitar_escritura(request, ctx)
    n = await novedades.reportar(db, ctx, body)
    await db.commit()
    if body.prioridad == PrioridadNovedad.CRITICA:
        await run_in_threadpool(celery_app.send_task, NOVEDAD_CRITICA_TASK, args=[str(ctx.tenant_id), str(n.id)])
    return await consultas.novedad(db, ctx, n.id)


@router.get("/novedades/{novedad_id}", response_model=NovedadOut)
async def detalle_novedad(novedad_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> NovedadOut:
    return await consultas.novedad(db, ctx, novedad_id)


@router.post("/novedades/{novedad_id}/estado", response_model=NovedadOut)
async def avanzar_novedad(novedad_id: uuid.UUID, body: NovedadAvance, ctx: TenantCtx, db: DbSession) -> NovedadOut:
    """Siguiente paso del flujo (gestión, cotización, programación, ejecución, cierre o descarte)."""
    await novedades.avanzar(db, ctx, novedad_id, body)
    await db.commit()
    return await consultas.novedad(db, ctx, novedad_id)


# --- Recomendaciones ------------------------------------------------------------------------------------


@router.get("/recomendaciones", response_model=list[RecomendacionOut])
async def listar_recomendaciones(
    ctx: TenantCtx,
    db: DbSession,
    estado: EstadoRecomendacion | None = None,
    pendientes: bool = False,
    prioridad: PrioridadRecomendacion | None = None,
    activo_id: uuid.UUID | None = None,
    mias: bool = False,
) -> list[RecomendacionOut]:
    return await consultas.listar_recomendaciones(
        db, ctx, estado=estado, pendientes=pendientes, prioridad=prioridad, activo_id=activo_id, mias=mias
    )


@router.post("/recomendaciones", response_model=RecomendacionOut, status_code=status.HTTP_201_CREATED)
async def crear_recomendacion(
    body: RecomendacionIn, request: Request, ctx: TenantCtx, db: DbSession
) -> RecomendacionOut:
    await limitar_escritura(request, ctx)
    r = await recomendaciones.crear(db, ctx, body)
    await db.commit()
    return await consultas.recomendacion(db, ctx, r.id)


@router.patch("/recomendaciones/{recomendacion_id}", response_model=RecomendacionOut)
async def actualizar_recomendacion(
    recomendacion_id: uuid.UUID, body: RecomendacionUpdate, ctx: TenantCtx, db: DbSession
) -> RecomendacionOut:
    await recomendaciones.actualizar(db, ctx, recomendacion_id, body)
    await db.commit()
    return await consultas.recomendacion(db, ctx, recomendacion_id)


# --- Auditoría ---------------------------------------------------------------------------------------------


@router.get("/auditoria/{entidad}/{entidad_id}", response_model=list[AuditoriaOut])
async def auditoria(entidad: str, entidad_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> list[AuditoriaOut]:
    return await consultas.auditoria(db, ctx, entidad, entidad_id)
