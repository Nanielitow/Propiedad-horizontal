"""Piezas compartidas de la cartera: configuración, saldos pendientes y responsable de pago."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AplicacionPago,
    CargoCartera,
    CarteraConfig,
    ConceptoCartera,
    PagoCartera,
    Persona,
    SaldoCargo,
    UnidadPersona,
)
from app.models.enums import EstadoCargo, EstadoPagoCartera, RelacionUnidad, TipoConceptoCartera
from app.schemas.cartera import ConfigIn
from app.services.cartera.dominio import CERO, PUEDE_CONFIGURAR, CargoPendiente
from app.services.comun import Actor, NoEncontrado, ValidacionError, exigir, fijar_motivo


async def config(db: AsyncSession, actor: Actor) -> CarteraConfig | None:
    return await db.get(CarteraConfig, actor.tenant_id)


async def config_requerida(db: AsyncSession, actor: Actor) -> CarteraConfig:
    c = await config(db, actor)
    if c is None:
        raise ValidacionError("Configure primero la cartera: método de la cuota, vencimiento e intereses")
    return c


async def guardar_config(db: AsyncSession, actor: Actor, data: ConfigIn) -> CarteraConfig:
    exigir(actor, PUEDE_CONFIGURAR, "configurar la cartera")
    datos = data.model_dump(exclude={"motivo"})
    datos["tarifas_por_tipo"] = {k.value: str(v) for k, v in data.tarifas_por_tipo.items() if v > 0}
    if data.descuento_pct == 0:
        datos["dia_limite_descuento"] = None
    c = await config(db, actor)
    await fijar_motivo(db, data.motivo)
    if c is None:
        c = CarteraConfig(tenant_id=actor.tenant_id, **datos)
        db.add(c)
    else:
        for k, v in datos.items():
            setattr(c, k, v)
    await db.flush()
    await fijar_motivo(db, None)
    return c


async def concepto(
    db: AsyncSession, actor: Actor, *, codigo: str | None = None, concepto_id: uuid.UUID | None = None
) -> ConceptoCartera:
    q = select(ConceptoCartera).where(ConceptoCartera.tenant_id == actor.tenant_id)
    q = q.where(ConceptoCartera.codigo == codigo) if codigo else q.where(ConceptoCartera.id == concepto_id)
    c = await db.scalar(q)
    if c is None:
        raise NoEncontrado("Concepto de cartera no encontrado")
    return c


async def pendientes(db: AsyncSession, unidad_id: uuid.UUID) -> list[CargoPendiente]:
    """Cargos vigentes con saldo de una unidad, listos para imputar un pago."""
    filas = await db.execute(
        select(SaldoCargo.saldo, CargoCartera, ConceptoCartera.tipo)
        .join(CargoCartera, CargoCartera.id == SaldoCargo.id)
        .join(ConceptoCartera, ConceptoCartera.id == CargoCartera.concepto_id)
        .where(SaldoCargo.unidad_id == unidad_id, SaldoCargo.estado == EstadoCargo.VIGENTE, SaldoCargo.saldo > 0)
    )
    return [
        CargoPendiente(
            id=c.id,
            es_interes=tipo == TipoConceptoCartera.INTERES,
            fecha_vencimiento=c.fecha_vencimiento,
            fecha_causacion=c.fecha_causacion,
            valor=c.valor,
            saldo=saldo,
            descuento_pct=c.descuento_pct,
            fecha_limite_descuento=c.fecha_limite_descuento,
        )
        for saldo, c, tipo in filas.all()
    ]


async def saldo_unidad(db: AsyncSession, unidad_id: uuid.UUID, *, vencido_a: date | None = None) -> Decimal:
    q = select(func.coalesce(func.sum(SaldoCargo.saldo), 0)).where(
        SaldoCargo.unidad_id == unidad_id, SaldoCargo.estado == EstadoCargo.VIGENTE
    )
    if vencido_a is not None:
        q = q.where(SaldoCargo.fecha_vencimiento < vencido_a)
    return Decimal(await db.scalar(q) or 0)


async def saldos_a_favor(db: AsyncSession, unidad_id: uuid.UUID) -> list[tuple[PagoCartera, Decimal]]:
    """Pagos vigentes con dinero sin aplicar (del más antiguo al más reciente)."""
    aplicado = (
        select(func.coalesce(func.sum(AplicacionPago.valor), 0))
        .where(AplicacionPago.pago_id == PagoCartera.id)
        .correlate(PagoCartera)
        .scalar_subquery()
    )
    filas = await db.execute(
        select(PagoCartera, PagoCartera.valor - aplicado)
        .where(PagoCartera.unidad_id == unidad_id, PagoCartera.estado == EstadoPagoCartera.APLICADO)
        .order_by(PagoCartera.fecha_pago, PagoCartera.consecutivo)
    )
    return [(p, Decimal(d)) for p, d in filas.all() if Decimal(d) > CERO]


async def responsable(db: AsyncSession, unidad_id: uuid.UUID) -> tuple[uuid.UUID | None, str | None]:
    """Responsable de pago vigente; si no hay, el primer propietario."""
    filas = (
        await db.execute(
            select(Persona.id, Persona.nombre_completo, UnidadPersona.responsable_pago)
            .join(UnidadPersona, UnidadPersona.persona_id == Persona.id)
            .where(
                UnidadPersona.unidad_id == unidad_id,
                UnidadPersona.fecha_fin.is_(None),
                (UnidadPersona.responsable_pago.is_(True)) | (UnidadPersona.relacion == RelacionUnidad.PROPIETARIO),
            )
            .order_by(UnidadPersona.responsable_pago.desc(), UnidadPersona.fecha_inicio)
        )
    ).first()
    return (filas[0], filas[1]) if filas else (None, None)
