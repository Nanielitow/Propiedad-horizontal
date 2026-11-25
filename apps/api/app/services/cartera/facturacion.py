"""Facturación mensual: vista previa, emisión del periodo y anulación.

Emitir un periodo crea, en una transacción:
  1. la cuota ordinaria de cada unidad (por coeficiente o por tarifa del tipo),
     a nombre del responsable de pago vigente;
  2. los intereses de mora sobre el capital vencido (si la copropiedad los cobra);
  3. la aplicación automática de los saldos a favor.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AjusteCartera, AplicacionPago, CargoCartera, PagoCartera, PeriodoCartera, SaldoCargo, Unit
from app.models.enums import EstadoCargo, EstadoPagoCartera, EstadoPeriodo, MetodoCuota
from app.schemas.cartera import EmitirPeriodoIn
from app.services.cartera import comun
from app.services.cartera import dominio as d
from app.services.cartera.pagos import aplicar_saldos_a_favor
from app.services.comun import Actor, NoEncontrado, ValidacionError, exigir, fijar_motivo, hoy_bogota, pesos
from app.services.unidades.consultas import orden_unidad


@dataclass
class LineaFactura:
    unidad: Unit
    cuota: Decimal | None
    interes: Decimal
    capital_vencido: Decimal
    responsable_id: uuid.UUID | None
    responsable_nombre: str | None


@dataclass
class Prefactura:
    anio: int
    mes: int
    fecha_emision: date
    vencimiento: date
    limite_descuento: date | None
    metodo: MetodoCuota
    lineas: list[LineaFactura] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)

    @property
    def total_cuotas(self) -> Decimal:
        return sum((ln.cuota or d.CERO for ln in self.lineas), d.CERO)

    @property
    def total_intereses(self) -> Decimal:
        return sum((ln.interes for ln in self.lineas), d.CERO)

    @property
    def facturadas(self) -> int:
        return sum(1 for ln in self.lineas if ln.cuota)


async def _periodo_existente(db: AsyncSession, actor: Actor, anio: int, mes: int) -> PeriodoCartera | None:
    return await db.scalar(
        select(PeriodoCartera).where(
            PeriodoCartera.tenant_id == actor.tenant_id,
            PeriodoCartera.anio == anio,
            PeriodoCartera.mes == mes,
            PeriodoCartera.estado == EstadoPeriodo.EMITIDO,
        )
    )


async def prefacturar(db: AsyncSession, actor: Actor, data: EmitirPeriodoIn) -> Prefactura:
    exigir(actor, d.PUEDE_FACTURAR, "facturar la cartera")
    cfg = await comun.config_requerida(db, actor)
    hoy = hoy_bogota()
    emision = data.fecha_emision or hoy
    if emision > hoy:
        raise ValidacionError("La fecha de emisión no puede estar en el futuro")
    # Se admite facturar el mes en curso y el siguiente (hay quien emite el 25 para el mes que viene)
    siguiente = (hoy.year + (hoy.month == 12), hoy.month % 12 + 1)
    if (data.anio, data.mes) > siguiente:
        raise ValidacionError("Solo se puede facturar hasta el mes siguiente al actual")
    if await _periodo_existente(db, actor, data.anio, data.mes):
        raise ValidacionError(f"El periodo de {d.nombre_periodo(data.anio, data.mes)} ya fue emitido")

    fechas = d.fechas_periodo(
        data.anio, data.mes, cfg.dia_vencimiento, cfg.dia_limite_descuento if cfg.descuento_pct else None
    )
    venc, limite = fechas.vencimiento, fechas.limite_descuento
    pf = Prefactura(
        data.anio, data.mes, emision, max(venc, emision), limite if limite and limite >= emision else None, cfg.metodo
    )
    if venc < emision:
        pf.advertencias.append(
            f"La emisión es posterior al día de vencimiento ({venc:%d/%m}): las cuotas vencerán el {emision:%d/%m/%Y}"
        )
    if limite and pf.limite_descuento is None:
        pf.advertencias.append(
            "La fecha límite del descuento ya pasó: este periodo no tendrá descuento por pronto pago"
        )

    unidades = sorted(await db.scalars(select(Unit).where(Unit.activa.is_(True))), key=orden_unidad)
    # Capital vencido que genera interés, por unidad
    vencido = dict(
        (
            await db.execute(
                select(SaldoCargo.unidad_id, func.sum(SaldoCargo.saldo))
                .where(
                    SaldoCargo.estado == EstadoCargo.VIGENTE,
                    SaldoCargo.genera_interes.is_(True),
                    SaldoCargo.saldo > 0,
                    SaldoCargo.fecha_vencimiento < emision,
                )
                .group_by(SaldoCargo.unidad_id)
            )
        ).all()
    )
    sin_coef: list[str] = []
    for u in unidades:
        if cfg.metodo == MetodoCuota.COEFICIENTE:
            if u.coefficient is None:
                cuota = None
                if u.unidad_principal_id is None:
                    sin_coef.append(u.etiqueta)
            else:
                cuota = d.cuota_por_coeficiente(cfg.presupuesto_mensual or d.CERO, u.coefficient, cfg.redondeo)
        else:
            cuota = d.cuota_por_tipo(cfg.tarifas_por_tipo, u.tipo.value, cfg.redondeo)
        capital = Decimal(vencido.get(u.id) or 0)
        interes = d.interes_mora(capital, cfg.tasa_mora_mensual) if cfg.cobrar_intereses else d.CERO
        if not cuota and not interes:
            continue
        rid, rnombre = await comun.responsable(db, u.id)
        pf.lineas.append(LineaFactura(u, cuota, interes, capital, rid, rnombre))
    if sin_coef:
        pf.advertencias.append(
            f"{len(sin_coef)} unidad(es) sin coeficiente no se facturan: {', '.join(sin_coef[:10])}"
            + ("…" if len(sin_coef) > 10 else "")
        )
    if cfg.metodo == MetodoCuota.COEFICIENTE and cfg.presupuesto_mensual:
        diferencia = pf.total_cuotas - cfg.presupuesto_mensual
        if abs(diferencia) >= cfg.redondeo * 2:
            pf.advertencias.append(
                f"Las cuotas suman {pesos(pf.total_cuotas)} frente a un presupuesto de {pesos(cfg.presupuesto_mensual)} "
                "(revise que los coeficientes sumen 100 %)"
            )
    sin_resp = [ln.unidad.etiqueta for ln in pf.lineas if ln.responsable_nombre is None]
    if sin_resp:
        pf.advertencias.append(f"{len(sin_resp)} unidad(es) sin propietario ni responsable de pago registrado")
    if not pf.lineas:
        raise ValidacionError("No hay nada que facturar: revise los coeficientes o las tarifas de la configuración")
    return pf


async def emitir(db: AsyncSession, actor: Actor, data: EmitirPeriodoIn) -> PeriodoCartera:
    pf = await prefacturar(db, actor, data)
    cfg = await comun.config_requerida(db, actor)
    ordinaria = await comun.concepto(db, actor, codigo="ADMINISTRACION")
    intereses = await comun.concepto(db, actor, codigo="INTERESES_MORA")
    nombre = d.nombre_periodo(pf.anio, pf.mes)
    await fijar_motivo(db, None)
    periodo = PeriodoCartera(
        id=uuid.uuid4(),
        tenant_id=actor.tenant_id,
        anio=pf.anio,
        mes=pf.mes,
        fecha_emision=pf.fecha_emision,
        fecha_vencimiento=pf.vencimiento,
        fecha_limite_descuento=pf.limite_descuento,
        metodo=cfg.metodo,
        presupuesto_mensual=cfg.presupuesto_mensual,
        descuento_pct=cfg.descuento_pct if pf.limite_descuento else d.CERO,
        tasa_mora_mensual=cfg.tasa_mora_mensual if cfg.cobrar_intereses else None,
        unidades_facturadas=pf.facturadas,
        total_cuotas=pf.total_cuotas,
        total_intereses=pf.total_intereses,
        advertencias=pf.advertencias,
        emitido_por_id=actor.user_id,
    )
    db.add(periodo)
    await db.flush()
    con_descuento = bool(pf.limite_descuento and cfg.descuento_pct > 0)
    for ln in pf.lineas:
        comunes = {
            "tenant_id": actor.tenant_id,
            "unidad_id": ln.unidad.id,
            "periodo_id": periodo.id,
            "fecha_causacion": pf.fecha_emision,
            "fecha_vencimiento": pf.vencimiento,
            "responsable_persona_id": ln.responsable_id,
            "responsable_nombre": ln.responsable_nombre,
            "creado_por_id": actor.user_id,
        }
        if ln.cuota:
            db.add(
                CargoCartera(
                    id=uuid.uuid4(),
                    concepto_id=ordinaria.id,
                    descripcion=f"Cuota de administración {nombre}",
                    valor=ln.cuota,
                    genera_interes=ordinaria.genera_interes,
                    descuento_pct=cfg.descuento_pct if con_descuento else None,
                    fecha_limite_descuento=pf.limite_descuento if con_descuento else None,
                    **comunes,
                )
            )
        if ln.interes:
            db.add(
                CargoCartera(
                    id=uuid.uuid4(),
                    concepto_id=intereses.id,
                    descripcion=f"Intereses de mora {nombre} ({cfg.tasa_mora_mensual} % sobre {pesos(ln.capital_vencido)})",
                    valor=ln.interes,
                    genera_interes=False,
                    **comunes,
                )
            )
    await db.flush()
    # Saldos a favor (anticipos) cubren los nuevos cargos; con la fecha de emisión, aún aplica el descuento
    for ln in pf.lineas:
        await aplicar_saldos_a_favor(db, actor, ln.unidad.id, pf.fecha_emision)
    return periodo


async def anular_periodo(db: AsyncSession, actor: Actor, periodo_id: uuid.UUID, motivo: str) -> PeriodoCartera:
    """Solo si nadie ha pagado todavía sobre sus cargos (un error de configuración, por ejemplo)."""
    exigir(actor, d.PUEDE_ANULAR, "anular periodos de facturación")
    p = await db.get(PeriodoCartera, periodo_id)
    if p is None or p.tenant_id != actor.tenant_id:
        raise NoEncontrado("Periodo no encontrado")
    if p.estado == EstadoPeriodo.ANULADO:
        raise ValidacionError("El periodo ya está anulado")
    cargos = list(await db.scalars(select(CargoCartera).where(CargoCartera.periodo_id == p.id)))
    ids = [c.id for c in cargos]
    con_pagos = await db.scalar(
        select(func.count())
        .select_from(AplicacionPago)
        .join(PagoCartera, PagoCartera.id == AplicacionPago.pago_id)
        .where(AplicacionPago.cargo_id.in_(ids), PagoCartera.estado == EstadoPagoCartera.APLICADO)
    )
    ajustes = await db.scalar(select(func.count()).select_from(AjusteCartera).where(AjusteCartera.cargo_id.in_(ids)))
    if con_pagos or ajustes:
        raise ValidacionError(
            "Hay pagos o ajustes aplicados a cuotas de este periodo: anule primero esos pagos, "
            "o corrija con ajustes en lugar de anular el periodo"
        )
    ahora = datetime.now(UTC)
    await fijar_motivo(db, motivo)
    for c in cargos:
        if c.estado == EstadoCargo.VIGENTE:
            c.estado = EstadoCargo.ANULADO
            c.anulado_por_id = actor.user_id
            c.anulado_at = ahora
            c.motivo_anulacion = f"Periodo anulado: {motivo}"
    p.estado = EstadoPeriodo.ANULADO
    p.anulado_por_id = actor.user_id
    p.anulado_at = ahora
    p.motivo_anulacion = motivo
    await db.flush()
    await fijar_motivo(db, None)
    return p
