"""API del módulo de recaudos: catálogos, soportes y recaudos.

Los permisos por rol los aplica el servicio (y, debajo, RLS en PostgreSQL); los
errores de dominio se traducen a HTTP en app/main.py. Cada endpoint que escribe
hace commit explícito y, si se generaron alertas, encola su correo DESPUÉS.
"""

import uuid
from collections.abc import Iterable
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request, status
from fastapi.concurrency import run_in_threadpool

from app.api.deps import DbSession, TenantCtx
from app.core.config import get_settings
from app.core.rate_limit import DEMO_RECAUDOS_PER_IP_DAY, RECAUDOS_WRITES_PER_MINUTE, enforce, enforce_demo
from app.models import AlertaRecaudo
from app.models.enums import EstadoRecaudo, MedioPago, UserRole
from app.schemas.recaudos import (
    AnulacionIn,
    ConceptoCreate,
    ConceptoUpdate,
    RecaudoCreate,
    RecaudoUpdate,
    ReservaCreate,
    ReservaUpdate,
    SoporteUploadIn,
    ZonaCreate,
    ZonaUpdate,
)
from app.schemas.recaudos_out import (
    AuditoriaOut,
    ConceptoOut,
    CotizacionOut,
    PersonaOut,
    RecaudoDetalle,
    RecaudosPagina,
    ReservaOut,
    SoporteUploadOut,
    UnidadOut,
    ZonaOut,
)
from app.services.recaudos import catalogos, consultas, service
from app.services.recaudos.consultas import FiltroRecaudos
from app.services.recaudos.dominio import PUEDE_REGISTRAR, SOPORTE_TIPOS, ValidacionError, exigir
from app.services.storage.s3 import get_storage
from app.workers.celery_app import celery_app

router = APIRouter(prefix="/tenants/{tenant_id}/recaudos", tags=["recaudos"])

NOTIFICAR_TASK = "recaudos.notificar_alertas"


async def limitar_escritura(request: Request, ctx: TenantCtx) -> None:
    await enforce(request, RECAUDOS_WRITES_PER_MINUTE, str(ctx.user_id))
    await enforce_demo(request, DEMO_RECAUDOS_PER_IP_DAY, demo=ctx.is_demo)


async def confirmar(db: DbSession, ctx: TenantCtx, alertas: Iterable[AlertaRecaudo] = ()) -> None:
    """Commit y, solo si se guardó, aviso por correo de las alertas generadas."""
    await db.commit()
    ids = [str(a.id) for a in alertas]
    if ids:
        await run_in_threadpool(celery_app.send_task, NOTIFICAR_TASK, args=[str(ctx.tenant_id), ids])


# --- Catálogos ------------------------------------------------------------------------


@router.get("/conceptos", response_model=list[ConceptoOut])
async def listar_conceptos(ctx: TenantCtx, db: DbSession, incluir_inactivos: bool = False) -> list[ConceptoOut]:
    conceptos = await catalogos.listar_conceptos(db, ctx, incluir_inactivos=incluir_inactivos)
    return [ConceptoOut.model_validate(c) for c in conceptos]


@router.post("/conceptos", response_model=ConceptoOut, status_code=status.HTTP_201_CREATED)
async def crear_concepto(body: ConceptoCreate, ctx: TenantCtx, db: DbSession) -> ConceptoOut:
    concepto = await catalogos.crear_concepto(db, ctx, body)
    await confirmar(db, ctx)
    return ConceptoOut.model_validate(concepto)


@router.patch("/conceptos/{concepto_id}", response_model=ConceptoOut)
async def editar_concepto(concepto_id: uuid.UUID, body: ConceptoUpdate, ctx: TenantCtx, db: DbSession) -> ConceptoOut:
    concepto = await catalogos.editar_concepto(db, ctx, concepto_id, body)
    await confirmar(db, ctx)
    return ConceptoOut.model_validate(concepto)


@router.get("/zonas", response_model=list[ZonaOut])
async def listar_zonas(ctx: TenantCtx, db: DbSession, incluir_inactivas: bool = False) -> list[ZonaOut]:
    return [
        ZonaOut.model_validate(z) for z in await catalogos.listar_zonas(db, ctx, incluir_inactivas=incluir_inactivas)
    ]


@router.post("/zonas", response_model=ZonaOut, status_code=status.HTTP_201_CREATED)
async def crear_zona(body: ZonaCreate, ctx: TenantCtx, db: DbSession) -> ZonaOut:
    zona = await catalogos.crear_zona(db, ctx, body)
    await confirmar(db, ctx)
    return ZonaOut.model_validate(zona)


@router.patch("/zonas/{zona_id}", response_model=ZonaOut)
async def editar_zona(zona_id: uuid.UUID, body: ZonaUpdate, ctx: TenantCtx, db: DbSession) -> ZonaOut:
    zona = await catalogos.editar_zona(db, ctx, zona_id, body)
    await confirmar(db, ctx)
    return ZonaOut.model_validate(zona)


@router.get("/reservas", response_model=list[ReservaOut])
async def listar_reservas(
    ctx: TenantCtx, db: DbSession, desde: date | None = None, hasta: date | None = None
) -> list[ReservaOut]:
    return [ReservaOut.model_validate(r) for r in await catalogos.listar_reservas(db, ctx, desde=desde, hasta=hasta)]


@router.post("/reservas", response_model=ReservaOut, status_code=status.HTTP_201_CREATED)
async def crear_reserva(body: ReservaCreate, request: Request, ctx: TenantCtx, db: DbSession) -> ReservaOut:
    await limitar_escritura(request, ctx)
    reserva = await catalogos.crear_reserva(db, ctx, body)
    await confirmar(db, ctx)
    return ReservaOut.model_validate(reserva)


@router.patch("/reservas/{reserva_id}", response_model=ReservaOut)
async def editar_reserva(reserva_id: uuid.UUID, body: ReservaUpdate, ctx: TenantCtx, db: DbSession) -> ReservaOut:
    reserva = await catalogos.editar_reserva(db, ctx, reserva_id, body)
    await confirmar(db, ctx)
    return ReservaOut.model_validate(reserva)


@router.get("/personal", response_model=list[PersonaOut])
async def listar_personal(ctx: TenantCtx, db: DbSession, rol: UserRole | None = None) -> list[PersonaOut]:
    return [PersonaOut.model_validate(p) for p in await catalogos.listar_personal(db, ctx, rol)]


@router.get("/unidades", response_model=list[UnidadOut])
async def listar_unidades(ctx: TenantCtx, db: DbSession) -> list[UnidadOut]:
    unidades = await catalogos.listar_unidades(db, ctx)
    return [UnidadOut(id=u.id, etiqueta=f"Torre {u.tower} · {u.number}" if u.tower else u.number) for u in unidades]


# --- Soportes -------------------------------------------------------------------------


@router.post("/soportes/upload-url", response_model=SoporteUploadOut)
async def url_subida_soporte(body: SoporteUploadIn, request: Request, ctx: TenantCtx) -> SoporteUploadOut:
    """URL firmada para subir un soporte (PDF o imagen) directamente al almacenamiento."""
    exigir(ctx, PUEDE_REGISTRAR | {UserRole.CONTABILIDAD}, "adjuntar soportes")
    await limitar_escritura(request, ctx)
    extension = SOPORTE_TIPOS.get(body.content_type)
    if extension is None:
        raise ValidacionError("El soporte debe ser PDF, JPG, PNG o WEBP")
    settings = get_settings()
    if body.size_bytes > settings.max_upload_mb * 1024 * 1024:
        raise ValidacionError(f"El soporte supera el máximo de {settings.max_upload_mb} MB")
    storage = get_storage()
    key = storage.recaudo_soporte_key(ctx.tenant_id, extension)
    return SoporteUploadOut(
        soporte_key=key,
        upload_url=storage.presign_put(key, body.content_type),
        headers={"Content-Type": body.content_type},
        expires_in=settings.s3_presigned_ttl_seconds,
    )


# --- Recaudos ---------------------------------------------------------------------------


@router.get("/parqueadero/cotizar", response_model=CotizacionOut)
async def cotizar_parqueadero(
    concepto_id: uuid.UUID, hora_ingreso: datetime, hora_salida: datetime, ctx: TenantCtx, db: DbSession
) -> CotizacionOut:
    exigir(ctx, PUEDE_REGISTRAR, "cotizar el parqueadero")
    if hora_ingreso.tzinfo is None or hora_salida.tzinfo is None:
        raise ValidacionError("Las horas deben incluir zona horaria")
    c = await service.cotizar_parqueadero(db, ctx, concepto_id, hora_ingreso, hora_salida)
    return CotizacionOut(minutos=c.minutos, fracciones=c.fracciones, tarifa_sugerida=c.tarifa_sugerida)


@router.get("", response_model=RecaudosPagina)
async def buscar_recaudos(
    ctx: TenantCtx,
    db: DbSession,
    desde: date | None = None,
    hasta: date | None = None,
    mes: Annotated[int | None, Query(ge=1, le=12)] = None,
    anio: Annotated[int | None, Query(ge=2000, le=2100)] = None,
    concepto_id: uuid.UUID | None = None,
    medio_pago: MedioPago | None = None,
    estado: Annotated[list[EstadoRecaudo] | None, Query()] = None,
    usuario_id: uuid.UUID | None = None,
    unidad_id: uuid.UUID | None = None,
    pagador: Annotated[str | None, Query(max_length=100)] = None,
    placa: Annotated[str | None, Query(max_length=10)] = None,
    consecutivo: int | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> RecaudosPagina:
    filtro = FiltroRecaudos(
        desde=desde,
        hasta=hasta,
        mes=mes,
        anio=anio,
        concepto_id=concepto_id,
        medio_pago=medio_pago,
        estados=estado or [],
        usuario_id=usuario_id,
        unidad_id=unidad_id,
        pagador=pagador,
        placa=placa,
        consecutivo=consecutivo,
    )
    return await consultas.buscar_recaudos(db, ctx, filtro, page=page, page_size=page_size)


@router.post("", response_model=RecaudoDetalle, status_code=status.HTTP_201_CREATED)
async def registrar_recaudo(body: RecaudoCreate, request: Request, ctx: TenantCtx, db: DbSession) -> RecaudoDetalle:
    await limitar_escritura(request, ctx)
    recaudo = await service.registrar_recaudo(db, ctx, body)
    await confirmar(db, ctx)
    return await consultas.detalle_recaudo(db, ctx, recaudo.id)


@router.get("/{recaudo_id}", response_model=RecaudoDetalle)
async def detalle_recaudo(recaudo_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> RecaudoDetalle:
    return await consultas.detalle_recaudo(db, ctx, recaudo_id)


@router.patch("/{recaudo_id}", response_model=RecaudoDetalle)
async def editar_recaudo(recaudo_id: uuid.UUID, body: RecaudoUpdate, ctx: TenantCtx, db: DbSession) -> RecaudoDetalle:
    await service.editar_recaudo(db, ctx, recaudo_id, body)
    await confirmar(db, ctx)
    return await consultas.detalle_recaudo(db, ctx, recaudo_id)


@router.post("/{recaudo_id}/anular", response_model=RecaudoDetalle)
async def anular_recaudo(recaudo_id: uuid.UUID, body: AnulacionIn, ctx: TenantCtx, db: DbSession) -> RecaudoDetalle:
    _, alertas = await service.anular_recaudo_con_alertas(db, ctx, recaudo_id, body.motivo)
    await confirmar(db, ctx, alertas)
    return await consultas.detalle_recaudo(db, ctx, recaudo_id)


@router.post("/{recaudo_id}/verificar", response_model=RecaudoDetalle)
async def verificar_recaudo(recaudo_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> RecaudoDetalle:
    await service.verificar_recaudo(db, ctx, recaudo_id)
    await confirmar(db, ctx)
    return await consultas.detalle_recaudo(db, ctx, recaudo_id)


@router.get("/{recaudo_id}/auditoria", response_model=list[AuditoriaOut])
async def auditoria_recaudo(recaudo_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> list[AuditoriaOut]:
    return await consultas.auditoria_recaudo(db, ctx, recaudo_id)
