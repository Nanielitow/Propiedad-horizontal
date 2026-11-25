"""Pagos de cartera: registro, imputación (intereses primero, luego lo más antiguo),
descuento por pronto pago, saldo a favor, anulación y ajustes (condonación, corrección)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AjusteCartera, AplicacionPago, CargoCartera, PagoCartera, SaldoCargo, Unit
from app.models.enums import EstadoCargo, EstadoPagoCartera, TipoAjuste
from app.schemas.cartera import AjusteIn, PagoIn
from app.services.cartera import comun
from app.services.cartera.dominio import CERO, PUEDE_AJUSTAR, PUEDE_ANULAR, PUEDE_REGISTRAR_PAGO, Imputacion, imputar
from app.services.comun import Actor, NoEncontrado, ValidacionError, exigir, fijar_motivo, hoy_bogota, pesos
from app.services.recaudos.dominio import validar_soporte


@dataclass
class ResultadoPago:
    pago: PagoCartera
    imputacion: Imputacion
    saldo_pendiente: Decimal


async def _unidad(db: AsyncSession, actor: Actor, unidad_id: uuid.UUID) -> Unit:
    u = await db.get(Unit, unidad_id)
    if u is None or u.tenant_id != actor.tenant_id:
        raise NoEncontrado("Unidad no encontrada")
    return u


async def obtener_pago(db: AsyncSession, actor: Actor, pago_id: uuid.UUID) -> PagoCartera:
    p = await db.get(PagoCartera, pago_id)
    if p is None or p.tenant_id != actor.tenant_id:
        raise NoEncontrado("Pago no encontrado")
    return p


async def _aplicar(db: AsyncSession, actor: Actor, pago: PagoCartera, monto: Decimal, fecha: date) -> Imputacion:
    """Imputa `monto` del pago a los cargos pendientes de su unidad y registra aplicaciones y descuentos."""
    imp = imputar(monto, await comun.pendientes(db, pago.unidad_id), fecha)
    # El descuento primero: así el saldo del cargo ya refleja la rebaja cuando entra la aplicación
    for cargo_id, valor in imp.descuentos:
        db.add(
            AjusteCartera(
                id=uuid.uuid4(),
                tenant_id=actor.tenant_id,
                cargo_id=cargo_id,
                tipo=TipoAjuste.DESCUENTO_PRONTO_PAGO,
                valor=valor,
                motivo=f"Descuento por pronto pago (recibo {pago.consecutivo})",
                pago_id=pago.id,
                registrado_por_id=actor.user_id,
            )
        )
    await db.flush()
    for cargo_id, valor in imp.aplicaciones:
        db.add(
            AplicacionPago(id=uuid.uuid4(), tenant_id=actor.tenant_id, pago_id=pago.id, cargo_id=cargo_id, valor=valor)
        )
    await db.flush()
    return imp


async def registrar_pago(db: AsyncSession, actor: Actor, data: PagoIn) -> ResultadoPago:
    exigir(actor, PUEDE_REGISTRAR_PAGO, "registrar pagos de cartera")
    u = await _unidad(db, actor, data.unidad_id)
    if data.fecha_pago > hoy_bogota():
        raise ValidacionError("La fecha del pago no puede estar en el futuro")
    validar_soporte(actor, data.soporte_key)
    if data.referencia:
        repetido = await db.scalar(
            select(PagoCartera).where(
                PagoCartera.tenant_id == actor.tenant_id,
                PagoCartera.medio_pago == data.medio_pago,
                PagoCartera.referencia == data.referencia,
                PagoCartera.estado == EstadoPagoCartera.APLICADO,
            )
        )
        if repetido is not None:
            raise ValidacionError(
                f"La referencia {data.referencia} ya se registró en el recibo {repetido.consecutivo} "
                f"({pesos(repetido.valor)}): ¿es un pago duplicado?"
            )
    await fijar_motivo(db, None)
    pago = PagoCartera(
        id=uuid.uuid4(),
        tenant_id=actor.tenant_id,
        unidad_id=u.id,
        registrado_por_id=actor.user_id,
        **data.model_dump(exclude={"unidad_id"}),
    )
    db.add(pago)
    await db.flush()
    imp = await _aplicar(db, actor, pago, data.valor, data.fecha_pago)
    return ResultadoPago(pago, imp, await comun.saldo_unidad(db, u.id))


async def aplicar_saldos_a_favor(db: AsyncSession, actor: Actor, unidad_id: uuid.UUID, fecha: date) -> Decimal:
    """Al causarse nuevos cargos, el dinero sin aplicar de pagos anteriores los cubre."""
    total = CERO
    for pago, disponible in await comun.saldos_a_favor(db, unidad_id):
        imp = await _aplicar(db, actor, pago, disponible, fecha)
        total += imp.aplicado
        if imp.sobrante == disponible:  # ya no hay nada pendiente que cubrir
            break
    return total


async def anular_pago(db: AsyncSession, actor: Actor, pago_id: uuid.UUID, motivo: str) -> PagoCartera:
    """El pago y sus descuentos dejan de contar: los cargos recuperan su saldo (la vista lo recalcula)."""
    exigir(actor, PUEDE_ANULAR, "anular pagos")
    p = await obtener_pago(db, actor, pago_id)
    if p.estado == EstadoPagoCartera.ANULADO:
        raise ValidacionError(f"El recibo {p.consecutivo} ya está anulado")
    await fijar_motivo(db, motivo)
    p.estado = EstadoPagoCartera.ANULADO
    p.anulado_por_id = actor.user_id
    p.anulado_at = datetime.now(UTC)
    p.motivo_anulacion = motivo
    await db.flush()
    await fijar_motivo(db, None)
    return p


async def ajustar(db: AsyncSession, actor: Actor, data: AjusteIn) -> AjusteCartera:
    """Condonación (aprobada por el consejo o la asamblea) o corrección de un error de facturación."""
    exigir(actor, PUEDE_AJUSTAR, "condonar o corregir cargos")
    cargo = await db.get(CargoCartera, data.cargo_id)
    if cargo is None or cargo.tenant_id != actor.tenant_id:
        raise NoEncontrado("Cargo no encontrado")
    if cargo.estado != EstadoCargo.VIGENTE:
        raise ValidacionError("El cargo está anulado")
    saldo = await db.scalar(select(SaldoCargo.saldo).where(SaldoCargo.id == cargo.id))
    if data.valor > (saldo or CERO):
        raise ValidacionError(f"El ajuste ({pesos(data.valor)}) supera el saldo del cargo ({pesos(saldo or CERO)})")
    await fijar_motivo(db, data.motivo)
    a = AjusteCartera(
        id=uuid.uuid4(),
        tenant_id=actor.tenant_id,
        cargo_id=cargo.id,
        tipo=data.tipo,
        valor=data.valor,
        motivo=data.motivo,
        registrado_por_id=actor.user_id,
    )
    db.add(a)
    await db.flush()
    await fijar_motivo(db, None)
    return a
