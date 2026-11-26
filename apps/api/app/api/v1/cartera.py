"""API del módulo de cartera de cuotas de administración (docs/CARTERA.md)."""

import uuid
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select

from app.api.deps import DbSession, TenantCtx
from app.core.rate_limit import CARTERA_WRITES_PER_MINUTE, DEMO_CARTERA_PER_IP_DAY, enforce, enforce_demo
from app.models import (
    AjusteCartera,
    AplicacionPago,
    CargoCartera,
    ConceptoCartera,
    PazYSalvo,
    Persona,
    Tenant,
    UnidadPersona,
    Unit,
)
from app.models.enums import MedioPago
from app.schemas.cartera import AjusteIn, AnularIn, CargoManualIn, ConfigIn, EmitirPeriodoIn, PagoIn
from app.schemas.cartera_out import (
    AjusteOut,
    CargoOut,
    ConceptoOut,
    ConfigOut,
    EstadoCuenta,
    LineaPrefactura,
    MorososOut,
    PagoOut,
    PagosPagina,
    PazYSalvoOut,
    PeriodoOut,
    PrefacturaOut,
    ResultadoPagoOut,
    ResumenCartera,
)
from app.services.cartera import cargos, comun, consultas, documentos, facturacion, pagos, paz_y_salvo
from app.services.cartera import dominio as d
from app.services.cartera.consultas import FiltroPagos
from app.services.comun import NoEncontrado, exigir
from app.services.recaudos import exportar

router = APIRouter(prefix="/tenants/{tenant_id}/cartera", tags=["cartera"])

MIME = {"xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "pdf": "application/pdf"}


async def limitar(request: Request, ctx: TenantCtx) -> None:
    await enforce(request, CARTERA_WRITES_PER_MINUTE, str(ctx.user_id))
    await enforce_demo(request, DEMO_CARTERA_PER_IP_DAY, demo=ctx.is_demo)


async def _tenant(db: DbSession, ctx: TenantCtx) -> Tenant:
    t = await db.get(Tenant, ctx.tenant_id)
    assert t is not None
    return t


def _archivo(datos: bytes, nombre: str, formato: str, inline: bool = False) -> Response:
    disposicion = "inline" if inline else "attachment"
    return Response(
        content=datos,
        media_type=MIME[formato],
        headers={"Content-Disposition": f'{disposicion}; filename="{nombre}.{formato}"'},
    )


# --- Resumen y configuración ------------------------------------------------------------


@router.get("/resumen", response_model=ResumenCartera)
async def resumen(ctx: TenantCtx, db: DbSession) -> ResumenCartera:
    return await consultas.resumen(db, ctx)


@router.get("/config", response_model=ConfigOut | None)
async def ver_config(ctx: TenantCtx, db: DbSession) -> ConfigOut | None:
    c = await comun.config(db, ctx)
    return ConfigOut.model_validate(c) if c else None


@router.put("/config", response_model=ConfigOut)
async def guardar_config(body: ConfigIn, request: Request, ctx: TenantCtx, db: DbSession) -> ConfigOut:
    await limitar(request, ctx)
    c = await comun.guardar_config(db, ctx, body)
    await db.commit()
    await db.refresh(c)
    return ConfigOut.model_validate(c)


@router.get("/conceptos", response_model=list[ConceptoOut])
async def conceptos(ctx: TenantCtx, db: DbSession) -> list[ConceptoOut]:
    del ctx
    return [
        ConceptoOut.model_validate(c)
        for c in await db.scalars(select(ConceptoCartera).order_by(ConceptoCartera.nombre))
    ]


# --- Periodos -----------------------------------------------------------------------------


@router.get("/periodos", response_model=list[PeriodoOut])
async def listar_periodos(ctx: TenantCtx, db: DbSession) -> list[PeriodoOut]:
    return await consultas.periodos(db, ctx)


@router.post("/periodos/previa", response_model=PrefacturaOut)
async def prefacturar(body: EmitirPeriodoIn, ctx: TenantCtx, db: DbSession) -> PrefacturaOut:
    """Lo que se facturaría, sin guardar nada."""
    pf = await facturacion.prefacturar(db, ctx, body)
    return PrefacturaOut(
        anio=pf.anio,
        mes=pf.mes,
        nombre=d.nombre_periodo(pf.anio, pf.mes).capitalize(),
        fecha_emision=pf.fecha_emision,
        fecha_vencimiento=pf.vencimiento,
        fecha_limite_descuento=pf.limite_descuento,
        metodo=pf.metodo,
        total_cuotas=pf.total_cuotas,
        total_intereses=pf.total_intereses,
        unidades=pf.facturadas,
        lineas=[
            LineaPrefactura(
                unidad_id=ln.unidad.id,
                etiqueta=ln.unidad.etiqueta,
                responsable=ln.responsable_nombre,
                cuota=ln.cuota,
                capital_vencido=ln.capital_vencido,
                interes=ln.interes,
            )
            for ln in pf.lineas
        ],
        advertencias=pf.advertencias,
    )


@router.post("/periodos", response_model=PeriodoOut, status_code=status.HTTP_201_CREATED)
async def emitir(body: EmitirPeriodoIn, request: Request, ctx: TenantCtx, db: DbSession) -> PeriodoOut:
    await limitar(request, ctx)
    p = await facturacion.emitir(db, ctx, body)
    await db.commit()
    return next(x for x in await consultas.periodos(db, ctx) if x.id == p.id)


@router.get("/periodos/{periodo_id}/cargos", response_model=list[CargoOut])
async def cargos_periodo(periodo_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> list[CargoOut]:
    return await consultas.cargos_de_periodo(db, ctx, periodo_id)


@router.post("/periodos/{periodo_id}/anular", response_model=PeriodoOut)
async def anular_periodo(
    periodo_id: uuid.UUID, body: AnularIn, request: Request, ctx: TenantCtx, db: DbSession
) -> PeriodoOut:
    await limitar(request, ctx)
    await facturacion.anular_periodo(db, ctx, periodo_id, body.motivo)
    await db.commit()
    return next(x for x in await consultas.periodos(db, ctx) if x.id == periodo_id)


# --- Cargos manuales y ajustes ---------------------------------------------------------------


@router.post("/cargos", status_code=status.HTTP_201_CREATED, response_model=None)
async def crear_cargos(body: CargoManualIn, request: Request, ctx: TenantCtx, db: DbSession) -> dict[str, Any]:
    """Cuota extraordinaria, multa u otro cobro (uno o varios cargos por unidad)."""
    await limitar(request, ctx)
    creados = await cargos.crear_cargos(db, ctx, body)
    await db.commit()
    return {
        "cargos": len(creados),
        "unidades": len({c.unidad_id for c in creados}),
        "total": str(sum(c.valor for c in creados)),
    }


@router.post("/cargos/{cargo_id}/anular", response_model=None)
async def anular_cargo(
    cargo_id: uuid.UUID, body: AnularIn, request: Request, ctx: TenantCtx, db: DbSession
) -> dict[str, str]:
    await limitar(request, ctx)
    c = await cargos.anular_cargo(db, ctx, cargo_id, body.motivo)
    await db.commit()
    return {"id": str(c.id), "estado": c.estado.value}


@router.post("/ajustes", response_model=AjusteOut, status_code=status.HTTP_201_CREATED)
async def ajustar(body: AjusteIn, request: Request, ctx: TenantCtx, db: DbSession) -> AjusteOut:
    await limitar(request, ctx)
    a = await pagos.ajustar(db, ctx, body)
    await db.commit()
    await db.refresh(a)
    return AjusteOut.model_validate(a)


# --- Pagos -------------------------------------------------------------------------------------


@router.get("/pagos", response_model=PagosPagina)
async def buscar_pagos(
    ctx: TenantCtx,
    db: DbSession,
    desde: date | None = None,
    hasta: date | None = None,
    unidad_id: uuid.UUID | None = None,
    medio_pago: MedioPago | None = None,
    texto: Annotated[str | None, Query(max_length=100)] = None,
    incluir_anulados: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> PagosPagina:
    f = FiltroPagos(desde, hasta, unidad_id, medio_pago, incluir_anulados, texto)
    return await consultas.buscar_pagos(db, ctx, f, page=page, page_size=page_size)


@router.post("/pagos", response_model=ResultadoPagoOut, status_code=status.HTTP_201_CREATED)
async def registrar_pago(body: PagoIn, request: Request, ctx: TenantCtx, db: DbSession) -> ResultadoPagoOut:
    """Registra el pago y lo imputa: intereses primero, luego lo más antiguo; el sobrante queda a favor."""
    await limitar(request, ctx)
    r = await pagos.registrar_pago(db, ctx, body)
    salida = await consultas.resultado_pago(db, ctx, r)
    await db.commit()
    return salida


@router.get("/pagos/{pago_id}", response_model=PagoOut)
async def ver_pago(pago_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> PagoOut:
    return await consultas.pago(db, ctx, pago_id)


@router.get("/pagos/{pago_id}/recibo.pdf")
async def recibo(pago_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> Response:
    p = await consultas.pago(db, ctx, pago_id)
    filas = await db.execute(
        select(CargoCartera.id, CargoCartera.descripcion, AplicacionPago.valor)
        .join(AplicacionPago, AplicacionPago.cargo_id == CargoCartera.id)
        .where(AplicacionPago.pago_id == pago_id)
    )
    descuentos = dict(
        (
            await db.execute(
                select(AjusteCartera.cargo_id, AjusteCartera.valor).where(AjusteCartera.pago_id == pago_id)
            )
        ).all()
    )
    aplicaciones = [(desc, v, descuentos.get(cid, d.CERO)) for cid, desc, v in filas.all()]
    t = await _tenant(db, ctx)
    saldo = await comun.saldo_unidad(db, p.unidad_id)
    datos = await run_in_threadpool(
        lambda: documentos.recibo_pdf(copropiedad=t.name, nit=t.nit, p=p, aplicaciones=aplicaciones, saldo=saldo)
    )
    return _archivo(datos, f"recibo-{p.consecutivo}", "pdf", inline=True)


@router.post("/pagos/{pago_id}/anular", response_model=PagoOut)
async def anular_pago(pago_id: uuid.UUID, body: AnularIn, request: Request, ctx: TenantCtx, db: DbSession) -> PagoOut:
    await limitar(request, ctx)
    await pagos.anular_pago(db, ctx, pago_id, body.motivo)
    await db.commit()
    return await consultas.pago(db, ctx, pago_id)


# --- Estado de cuenta, morosos y paz y salvo ----------------------------------------------------


@router.get("/unidades/{unidad_id}/estado-cuenta", response_model=None)
async def estado_cuenta(
    unidad_id: uuid.UUID, ctx: TenantCtx, db: DbSession, formato: Literal["json", "xlsx", "pdf"] = "json"
) -> EstadoCuenta | Response:
    e = await consultas.estado_cuenta(db, ctx, unidad_id)
    if formato == "json":
        return e
    r = documentos.reporte_estado_cuenta(e)
    datos = await run_in_threadpool(exportar.a_pdf if formato == "pdf" else exportar.a_excel, r)
    return _archivo(datos, f"estado-cuenta-{e.unidad}-{e.corte.isoformat()}", formato)


@router.get("/mi-cartera", response_model=list[EstadoCuenta])
async def mi_cartera(ctx: TenantCtx, db: DbSession) -> list[EstadoCuenta]:
    """Para el residente: el estado de cuenta de cada una de sus unidades principales."""
    ids = list(
        await db.scalars(
            select(UnidadPersona.unidad_id)
            .join(Persona, Persona.id == UnidadPersona.persona_id)
            .join(Unit, Unit.id == UnidadPersona.unidad_id)
            .where(
                Persona.user_id == ctx.user_id, UnidadPersona.fecha_fin.is_(None), Unit.unidad_principal_id.is_(None)
            )
            .distinct()
        )
    )
    return [await consultas.estado_cuenta(db, ctx, i) for i in ids]


@router.get("/morosos", response_model=None)
async def morosos(
    ctx: TenantCtx,
    db: DbSession,
    dias_minimos: Annotated[int, Query(ge=1, le=3650)] = 1,
    texto: Annotated[str | None, Query(max_length=100)] = None,
    formato: Literal["json", "xlsx", "pdf"] = "json",
) -> MorososOut | Response:
    m = await consultas.morosos(db, ctx, dias_minimos=dias_minimos, texto=texto)
    if formato == "json":
        return m
    t = await _tenant(db, ctx)
    datos = await run_in_threadpool(
        exportar.a_pdf if formato == "pdf" else exportar.a_excel, documentos.reporte_morosos(m, t.name)
    )
    return _archivo(datos, f"morosos-{m.corte.isoformat()}", formato)


@router.post("/unidades/{unidad_id}/paz-y-salvo", response_model=PazYSalvoOut, status_code=status.HTTP_201_CREATED)
async def expedir_paz_y_salvo(unidad_id: uuid.UUID, request: Request, ctx: TenantCtx, db: DbSession) -> PazYSalvoOut:
    await limitar(request, ctx)
    p = await paz_y_salvo.emitir(db, ctx, unidad_id)
    await db.commit()
    return PazYSalvoOut.model_validate(p)


@router.get("/paz-y-salvo/{paz_id}.pdf")
async def paz_y_salvo_pdf(paz_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> Response:
    exigir(ctx, d.PUEDE_PAZ_Y_SALVO | d.PUEDE_VER, "consultar paz y salvos")
    p = await db.get(PazYSalvo, paz_id)
    if p is None or p.tenant_id != ctx.tenant_id:
        raise NoEncontrado("Paz y salvo no encontrado")
    u = await db.get(Unit, p.unidad_id)
    t = await _tenant(db, ctx)
    datos = await run_in_threadpool(
        lambda: documentos.paz_y_salvo_pdf(
            copropiedad=t.name,
            nit=t.nit,
            unidad=u.etiqueta if u else "",
            titular=p.titular_nombre,
            consecutivo=p.consecutivo,
            emision=p.fecha_emision,
            valido_hasta=p.valido_hasta,
            codigo=p.codigo_verificacion,
        )
    )
    return _archivo(datos, f"paz-y-salvo-{u.etiqueta if u else p.consecutivo}", "pdf", inline=True)


@router.get("/paz-y-salvo/verificar/{codigo}", response_model=None)
async def verificar_paz_y_salvo(codigo: str, ctx: TenantCtx, db: DbSession) -> dict[str, Any]:
    exigir(ctx, d.PUEDE_VER, "verificar paz y salvos")
    p = await paz_y_salvo.verificar(db, ctx, codigo)
    u = await db.get(Unit, p.unidad_id)
    return {
        "valido": True,
        "consecutivo": p.consecutivo,
        "unidad": u.etiqueta if u else "",
        "titular": p.titular_nombre,
        "fecha_emision": p.fecha_emision.isoformat(),
        "valido_hasta": p.valido_hasta.isoformat(),
    }
