"""Consultas de la cartera: resumen, estado de cuenta, morosos por antigüedad, periodos y pagos.

La RLS decide qué filas ve cada rol (el residente, solo sus unidades); aquí se arma la lectura.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import Select, func, literal_column, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AjusteCartera,
    AplicacionPago,
    CargoCartera,
    ConceptoCartera,
    PagoCartera,
    PeriodoCartera,
    Persona,
    SaldoCargo,
    Tenant,
    UnidadPersona,
    Unit,
    User,
)
from app.models.enums import EstadoCargo, EstadoPagoCartera, EstadoPeriodo, MedioPago, TipoAjuste, UserRole
from app.schemas.cartera_out import (
    AplicacionOut,
    CargoOut,
    EstadoCuenta,
    Moroso,
    MorososOut,
    Movimiento,
    PagoOut,
    PagosPagina,
    PeriodoOut,
    ResultadoPagoOut,
    ResumenCartera,
)
from app.services.cartera import comun
from app.services.cartera import dominio as d
from app.services.cartera.pagos import ResultadoPago
from app.services.comun import Actor, NoEncontrado, exigir, hoy_bogota
from app.services.unidades.consultas import orden_unidad

R = UserRole
_MES = literal_column("'YYYY-MM'")  # literal (no parámetro): el GROUP BY debe ser idéntico al SELECT


def _ver(actor: Actor) -> None:
    if actor.role != R.RESIDENTE:
        exigir(actor, d.PUEDE_VER, "consultar la cartera")


async def _etiquetas(db: AsyncSession) -> dict[uuid.UUID, Unit]:
    return {u.id: u for u in await db.scalars(select(Unit))}


def _aplicado_por_pago() -> Select[tuple[uuid.UUID, Decimal]]:
    return select(AplicacionPago.pago_id, func.sum(AplicacionPago.valor)).group_by(AplicacionPago.pago_id)


# --- Periodos ------------------------------------------------------------------------


async def _recaudado_por_periodo(db: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[Decimal, Decimal]]:
    """(lo aplicado + descontado, saldo pendiente) de los cargos de cada periodo."""
    filas = await db.execute(
        select(SaldoCargo.periodo_id, func.sum(SaldoCargo.aplicado + SaldoCargo.ajustado), func.sum(SaldoCargo.saldo))
        .where(SaldoCargo.periodo_id.in_(ids), SaldoCargo.estado == EstadoCargo.VIGENTE)
        .group_by(SaldoCargo.periodo_id)
    )
    return {pid: (Decimal(a or 0), Decimal(s or 0)) for pid, a, s in filas.all()}


def periodo_out(p: PeriodoCartera, recaudado: Decimal, pendiente: Decimal) -> PeriodoOut:
    return PeriodoOut(
        id=p.id,
        anio=p.anio,
        mes=p.mes,
        nombre=d.nombre_periodo(p.anio, p.mes).capitalize(),
        estado=p.estado,
        fecha_emision=p.fecha_emision,
        fecha_vencimiento=p.fecha_vencimiento,
        fecha_limite_descuento=p.fecha_limite_descuento,
        metodo=p.metodo,
        presupuesto_mensual=p.presupuesto_mensual,
        descuento_pct=p.descuento_pct,
        tasa_mora_mensual=p.tasa_mora_mensual,
        unidades_facturadas=p.unidades_facturadas,
        total_cuotas=p.total_cuotas,
        total_intereses=p.total_intereses,
        recaudado=recaudado,
        pendiente=pendiente,
        advertencias=[str(a) for a in p.advertencias],
        motivo_anulacion=p.motivo_anulacion,
    )


async def periodos(db: AsyncSession, actor: Actor, *, limite: int = 24) -> list[PeriodoOut]:
    _ver(actor)
    ps = list(
        await db.scalars(
            select(PeriodoCartera)
            .order_by(PeriodoCartera.anio.desc(), PeriodoCartera.mes.desc(), PeriodoCartera.created_at.desc())
            .limit(limite)
        )
    )
    rec = await _recaudado_por_periodo(db, [p.id for p in ps])
    return [periodo_out(p, *rec.get(p.id, (d.CERO, d.CERO))) for p in ps]


async def cargos_de_periodo(db: AsyncSession, actor: Actor, periodo_id: uuid.UUID) -> list[CargoOut]:
    _ver(actor)
    return await _cargos(db, select(CargoCartera).where(CargoCartera.periodo_id == periodo_id))


async def _cargos(db: AsyncSession, q: Select[tuple[CargoCartera]], corte: date | None = None) -> list[CargoOut]:
    corte = corte or hoy_bogota()
    unidades = await _etiquetas(db)
    conceptos = {c.id: c for c in await db.scalars(select(ConceptoCartera))}
    filas = await db.execute(q.add_columns(SaldoCargo.saldo).join(SaldoCargo, SaldoCargo.id == CargoCartera.id))
    salida = []
    for c, saldo in filas.all():
        con = conceptos[c.concepto_id]
        salida.append(
            CargoOut(
                id=c.id,
                unidad_id=c.unidad_id,
                unidad=unidades[c.unidad_id].etiqueta if c.unidad_id in unidades else "",
                concepto=con.nombre,
                tipo_concepto=con.tipo,
                descripcion=c.descripcion,
                valor=c.valor,
                saldo=saldo,
                fecha_causacion=c.fecha_causacion,
                fecha_vencimiento=c.fecha_vencimiento,
                dias_mora=d.dias_mora(c.fecha_vencimiento, corte) if saldo > 0 else 0,
                responsable_nombre=c.responsable_nombre,
                estado=c.estado,
                periodo_id=c.periodo_id,
            )
        )
    salida.sort(
        key=lambda x: (
            orden_unidad(unidades[x.unidad_id]) if x.unidad_id in unidades else ("", 0, 0, ""),
            x.fecha_vencimiento,
        )
    )
    return salida


# --- Pagos -----------------------------------------------------------------------------


async def _pagos_out(db: AsyncSession, pagos: list[PagoCartera]) -> list[PagoOut]:
    ids = [p.id for p in pagos]
    aplicado = dict((await db.execute(_aplicado_por_pago().where(AplicacionPago.pago_id.in_(ids)))).all())
    descuentos = dict(
        (
            await db.execute(
                select(AjusteCartera.pago_id, func.sum(AjusteCartera.valor))
                .where(AjusteCartera.pago_id.in_(ids))
                .group_by(AjusteCartera.pago_id)
            )
        ).all()
    )
    unidades = await _etiquetas(db)
    usuarios = dict(
        (
            await db.execute(select(User.id, User.full_name).where(User.id.in_({p.registrado_por_id for p in pagos})))
        ).all()
    )
    out = []
    for p in pagos:
        ap = Decimal(aplicado.get(p.id) or 0)
        out.append(
            PagoOut(
                id=p.id,
                consecutivo=p.consecutivo,
                unidad_id=p.unidad_id,
                unidad=unidades[p.unidad_id].etiqueta if p.unidad_id in unidades else "",
                fecha_pago=p.fecha_pago,
                valor=p.valor,
                aplicado=ap,
                a_favor=p.valor - ap if p.estado == EstadoPagoCartera.APLICADO else d.CERO,
                descuentos=Decimal(descuentos.get(p.id) or 0),
                medio_pago=p.medio_pago,
                referencia=p.referencia,
                pagador_nombre=p.pagador_nombre,
                tiene_soporte=bool(p.soporte_key),
                observaciones=p.observaciones,
                estado=p.estado,
                registrado_por=(usuarios.get(p.registrado_por_id) or "").split(" (")[0] or None,
                created_at=p.created_at,
                motivo_anulacion=p.motivo_anulacion,
            )
        )
    return out


async def pago(db: AsyncSession, actor: Actor, pago_id: uuid.UUID) -> PagoOut:
    _ver(actor)
    p = await db.get(PagoCartera, pago_id)
    if p is None or p.tenant_id != actor.tenant_id:
        raise NoEncontrado("Pago no encontrado")
    return (await _pagos_out(db, [p]))[0]


@dataclass(frozen=True)
class FiltroPagos:
    desde: date | None = None
    hasta: date | None = None
    unidad_id: uuid.UUID | None = None
    medio_pago: MedioPago | None = None
    incluir_anulados: bool = False
    texto: str | None = None  # referencia, pagador o número de recibo


async def buscar_pagos(
    db: AsyncSession, actor: Actor, f: FiltroPagos, *, page: int = 1, page_size: int = 50
) -> PagosPagina:
    _ver(actor)
    q = select(PagoCartera)
    if not f.incluir_anulados:
        q = q.where(PagoCartera.estado == EstadoPagoCartera.APLICADO)
    if f.desde:
        q = q.where(PagoCartera.fecha_pago >= f.desde)
    if f.hasta:
        q = q.where(PagoCartera.fecha_pago <= f.hasta)
    if f.unidad_id:
        q = q.where(PagoCartera.unidad_id == f.unidad_id)
    if f.medio_pago:
        q = q.where(PagoCartera.medio_pago == f.medio_pago)
    if f.texto and f.texto.strip():
        t = f.texto.strip()
        cond = [PagoCartera.referencia.ilike(f"%{t}%"), PagoCartera.pagador_nombre.ilike(f"%{t}%")]
        if t.isdigit():
            cond.append(PagoCartera.consecutivo == int(t))
        q = q.where(or_(*cond))
    sub = q.subquery()
    total, total_valor = (
        await db.execute(select(func.count(), func.coalesce(func.sum(sub.c.valor), 0)).select_from(sub))
    ).one()
    ps = list(
        await db.scalars(
            q.order_by(PagoCartera.fecha_pago.desc(), PagoCartera.consecutivo.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return PagosPagina(
        items=await _pagos_out(db, ps), total=total, total_valor=Decimal(total_valor), page=page, page_size=page_size
    )


async def resultado_pago(db: AsyncSession, actor: Actor, r: ResultadoPago) -> ResultadoPagoOut:
    descripciones = dict(
        (
            await db.execute(
                select(CargoCartera.id, CargoCartera.descripcion).where(CargoCartera.unidad_id == r.pago.unidad_id)
            )
        ).all()
    )
    desc = dict(r.imputacion.descuentos)
    return ResultadoPagoOut(
        pago=(await _pagos_out(db, [r.pago]))[0],
        aplicaciones=[
            AplicacionOut(
                cargo_id=cid, descripcion=descripciones.get(cid, ""), valor=v, descuento=desc.get(cid, d.CERO)
            )
            for cid, v in r.imputacion.aplicaciones
        ],
        a_favor=r.imputacion.sobrante,
        saldo_pendiente=r.saldo_pendiente,
    )


# --- Estado de cuenta ---------------------------------------------------------------------


async def estado_cuenta(db: AsyncSession, actor: Actor, unidad_id: uuid.UUID) -> EstadoCuenta:
    _ver(actor)
    u = await db.get(Unit, unidad_id)  # RLS: el residente solo ve sus unidades
    if u is None or u.tenant_id != actor.tenant_id:
        raise NoEncontrado("Unidad no encontrada")
    corte = hoy_bogota()
    tenant = await db.get(Tenant, actor.tenant_id)
    cargos = await _cargos(db, select(CargoCartera).where(CargoCartera.unidad_id == u.id), corte)
    pagos = list(await db.scalars(select(PagoCartera).where(PagoCartera.unidad_id == u.id)))
    pagos_out = await _pagos_out(db, pagos)
    ajustes = list(
        await db.execute(
            select(AjusteCartera, CargoCartera.descripcion)
            .join(CargoCartera, CargoCartera.id == AjusteCartera.cargo_id)
            .where(CargoCartera.unidad_id == u.id)
        )
    )
    pago_estado = {p.id: p.estado for p in pagos}

    movs: list[tuple[date, int, Movimiento]] = []
    for c in cargos:
        anulado = c.estado == EstadoCargo.ANULADO
        movs.append(
            (
                c.fecha_causacion,
                0,
                Movimiento(
                    fecha=c.fecha_causacion,
                    tipo="CARGO",
                    descripcion=c.descripcion,
                    cargo=c.valor,
                    abono=d.CERO,
                    saldo=d.CERO,
                    anulado=anulado,
                    referencia_id=c.id,
                ),
            )
        )
    for p in pagos_out:
        anulado = p.estado == EstadoPagoCartera.ANULADO
        texto = f"Pago recibo {p.consecutivo} · {p.medio_pago.value.lower()}" + (
            f" · {p.referencia}" if p.referencia else ""
        )
        movs.append(
            (
                p.fecha_pago,
                1,
                Movimiento(
                    fecha=p.fecha_pago,
                    tipo="PAGO",
                    descripcion=texto,
                    cargo=d.CERO,
                    abono=p.valor,
                    saldo=d.CERO,
                    anulado=anulado,
                    referencia_id=p.id,
                    consecutivo=p.consecutivo,
                ),
            )
        )
    for a, descripcion in ajustes:
        anulado = a.pago_id is not None and pago_estado.get(a.pago_id) == EstadoPagoCartera.ANULADO
        etiqueta = {
            TipoAjuste.DESCUENTO_PRONTO_PAGO: "Descuento por pronto pago",
            TipoAjuste.CONDONACION: "Condonación",
            TipoAjuste.CORRECCION: "Corrección",
        }[a.tipo]
        fecha = a.created_at.date()
        movs.append(
            (
                fecha,
                2,
                Movimiento(
                    fecha=fecha,
                    tipo="AJUSTE",
                    descripcion=f"{etiqueta}: {descripcion}",
                    cargo=d.CERO,
                    abono=a.valor,
                    saldo=d.CERO,
                    anulado=anulado,
                    referencia_id=a.id,
                ),
            )
        )
    movs.sort(key=lambda m: (m[0], m[1]))
    acumulado = d.CERO
    movimientos = []
    for _, _, m in movs:
        if not m.anulado:
            acumulado += m.cargo - m.abono
        m.saldo = acumulado
        movimientos.append(m)

    pendientes = [c for c in cargos if c.saldo > 0]
    vencido = sum((c.saldo for c in pendientes if c.fecha_vencimiento < corte), d.CERO)
    total = sum((c.saldo for c in pendientes), d.CERO)
    a_favor = sum((p.a_favor for p in pagos_out), d.CERO)
    _, responsable = await comun.responsable(db, u.id) if actor.role != R.CONSEJO else (None, None)
    if responsable is None and cargos:
        responsable = max(cargos, key=lambda c: c.fecha_causacion).responsable_nombre
    vivos = [p for p in pagos_out if p.estado == EstadoPagoCartera.APLICADO]
    return EstadoCuenta(
        unidad_id=u.id,
        unidad=u.etiqueta,
        responsable=responsable,
        copropiedad=tenant.name if tenant else "",
        corte=corte,
        saldo_total=total,
        saldo_vencido=vencido,
        saldo_corriente=total - vencido,
        saldo_a_favor=a_favor,
        dias_mora=max((c.dias_mora for c in pendientes), default=0),
        edades=d.edades(((c.fecha_vencimiento, c.saldo) for c in pendientes), corte),
        al_dia=vencido == 0,
        pendientes=sorted(pendientes, key=lambda c: c.fecha_vencimiento),
        movimientos=movimientos,
        ultimo_pago=max((p.fecha_pago for p in vivos), default=None),
    )


# --- Morosos y resumen ------------------------------------------------------------------------


async def _saldos_vigentes(db: AsyncSession) -> list[tuple[uuid.UUID, date, Decimal, uuid.UUID | None]]:
    filas = await db.execute(
        select(SaldoCargo.unidad_id, SaldoCargo.fecha_vencimiento, SaldoCargo.saldo, SaldoCargo.periodo_id).where(
            SaldoCargo.estado == EstadoCargo.VIGENTE, SaldoCargo.saldo > 0
        )
    )
    return [(u, f, Decimal(s), p) for u, f, s, p in filas.all()]


async def _ultimos_pagos(db: AsyncSession) -> dict[uuid.UUID, date]:
    return dict(
        (
            await db.execute(
                select(PagoCartera.unidad_id, func.max(PagoCartera.fecha_pago))
                .where(PagoCartera.estado == EstadoPagoCartera.APLICADO)
                .group_by(PagoCartera.unidad_id)
            )
        ).all()
    )


async def morosos(db: AsyncSession, actor: Actor, *, dias_minimos: int = 1, texto: str | None = None) -> MorososOut:
    exigir(actor, d.PUEDE_VER, "consultar los morosos")
    corte = hoy_bogota()
    unidades = await _etiquetas(db)
    por_unidad: dict[uuid.UUID, list[tuple[date, Decimal]]] = defaultdict(list)
    for uid, venc, saldo, _ in await _saldos_vigentes(db):
        por_unidad[uid].append((venc, saldo))
    ultimos = await _ultimos_pagos(db)
    # Responsable y teléfono: del directorio si el rol lo ve; si no, el nombre guardado en el cargo
    responsables: dict[uuid.UUID, tuple[str, str | None]] = {}
    if actor.role in (R.ADMIN, R.CONTABILIDAD, R.AUXILIAR):
        filas = await db.execute(
            select(UnidadPersona.unidad_id, Persona.nombre_completo, Persona.telefono)
            .join(Persona, Persona.id == UnidadPersona.persona_id)
            .where(UnidadPersona.fecha_fin.is_(None), UnidadPersona.responsable_pago.is_(True))
        )
        responsables = {u: (n, t) for u, n, t in filas.all()}
    nombres_cargo = dict(
        (
            await db.execute(
                select(CargoCartera.unidad_id, func.max(CargoCartera.responsable_nombre)).group_by(
                    CargoCartera.unidad_id
                )
            )
        ).all()
    )
    items = []
    for uid, saldos in por_unidad.items():
        vencidos = [(v, s) for v, s in saldos if v < corte]
        if not vencidos:
            continue
        dias = max(d.dias_mora(v, corte) for v, _ in vencidos)
        if dias < dias_minimos:
            continue
        u = unidades.get(uid)
        nombre, tel = responsables.get(uid, (nombres_cargo.get(uid), None))
        etiqueta = u.etiqueta if u else ""
        if texto and texto.strip().lower() not in f"{etiqueta} {nombre or ''}".lower():
            continue
        items.append(
            Moroso(
                unidad_id=uid,
                unidad=etiqueta,
                responsable=nombre,
                telefono=tel,
                saldo_total=sum((s for _, s in saldos), d.CERO),
                saldo_vencido=sum((s for _, s in vencidos), d.CERO),
                edades=d.edades(saldos, corte),
                dias_mora=dias,
                cuotas_vencidas=len(vencidos),
                ultimo_pago=ultimos.get(uid),
            )
        )
    items.sort(key=lambda m: (-m.saldo_vencido, m.unidad))
    total_edades = dict.fromkeys(d.RANGOS, d.CERO)
    for m in items:
        for k, v in m.edades.items():
            total_edades[k] += v
    return MorososOut(
        corte=corte, items=items, total_vencido=sum((m.saldo_vencido for m in items), d.CERO), edades=total_edades
    )


async def resumen(db: AsyncSession, actor: Actor) -> ResumenCartera:
    exigir(actor, d.PUEDE_VER, "consultar la cartera")
    corte = hoy_bogota()
    configurada = await comun.config(db, actor) is not None
    saldos = await _saldos_vigentes(db)
    total = sum((s for _, _, s, _ in saldos), d.CERO)
    vencido = sum((s for _, v, s, _ in saldos if v < corte), d.CERO)
    en_mora = {u for u, v, _, _ in saldos if v < corte}

    pagos_vivos = (
        select(PagoCartera.id, PagoCartera.valor).where(PagoCartera.estado == EstadoPagoCartera.APLICADO).subquery()
    )
    aplicado = select(func.coalesce(func.sum(AplicacionPago.valor), 0)).where(
        AplicacionPago.pago_id.in_(select(pagos_vivos.c.id))
    )
    a_favor = Decimal(await db.scalar(select(func.coalesce(func.sum(pagos_vivos.c.valor), 0))) or 0) - Decimal(
        await db.scalar(aplicado) or 0
    )

    ultimos = await periodos(db, actor, limite=6)
    actual = next(
        (p for p in ultimos if p.anio == corte.year and p.mes == corte.month and p.estado == EstadoPeriodo.EMITIDO),
        None,
    )
    inicio_mes = corte.replace(day=1)
    recaudado_mes = Decimal(
        await db.scalar(
            select(func.coalesce(func.sum(PagoCartera.valor), 0)).where(
                PagoCartera.estado == EstadoPagoCartera.APLICADO,
                PagoCartera.fecha_pago >= inicio_mes,
                PagoCartera.fecha_pago <= corte,
            )
        )
        or 0
    )
    facturado = (actual.total_cuotas + actual.total_intereses) if actual else d.CERO
    pct = (actual.recaudado / facturado * 100).quantize(Decimal("0.1")) if actual and facturado else None

    # Últimos 12 meses: lo causado vs. lo pagado en cada mes
    meses: list[tuple[int, int]] = []
    a, m = corte.year, corte.month
    for _ in range(12):
        meses.append((a, m))
        a, m = (a - 1, 12) if m == 1 else (a, m - 1)
    meses.reverse()
    desde = date(*meses[0], 1)
    causado = dict(
        (
            await db.execute(
                select(func.to_char(CargoCartera.fecha_causacion, _MES), func.sum(CargoCartera.valor))
                .where(CargoCartera.estado == EstadoCargo.VIGENTE, CargoCartera.fecha_causacion >= desde)
                .group_by(func.to_char(CargoCartera.fecha_causacion, _MES))
            )
        ).all()
    )
    pagado = dict(
        (
            await db.execute(
                select(func.to_char(PagoCartera.fecha_pago, _MES), func.sum(PagoCartera.valor))
                .where(PagoCartera.estado == EstadoPagoCartera.APLICADO, PagoCartera.fecha_pago >= desde)
                .group_by(func.to_char(PagoCartera.fecha_pago, _MES))
            )
        ).all()
    )
    serie = []
    for a, m in meses:
        k = f"{a}-{m:02d}"
        serie.append(
            {
                "mes": k,
                "etiqueta": d.MESES[m - 1][:3].capitalize(),
                "facturado": str(causado.get(k) or 0),
                "recaudado": str(pagado.get(k) or 0),
            }
        )

    activas = await db.scalar(
        select(func.count()).select_from(Unit).where(Unit.activa.is_(True), Unit.unidad_principal_id.is_(None))
    )
    return ResumenCartera(
        corte=corte,
        configurada=configurada,
        cartera_total=total,
        cartera_vencida=vencido,
        saldo_a_favor=a_favor,
        edades=d.edades(((v, s) for _, v, s, _ in saldos), corte),
        unidades_en_mora=len(en_mora),
        unidades_al_dia=max(0, (activas or 0) - len(en_mora)),
        unidades_facturadas=actual.unidades_facturadas if actual else 0,
        facturado_mes=facturado,
        recaudado_mes=recaudado_mes,
        recaudo_pct=pct,
        ultimos_periodos=ultimos,
        recaudo_mensual=serie,
    )
