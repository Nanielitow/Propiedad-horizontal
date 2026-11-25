"""Cargos manuales (cuota extraordinaria aprobada en asamblea, multas, otros) y su anulación."""

import calendar
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AjusteCartera, AplicacionPago, CargoCartera, PagoCartera, Unit
from app.models.enums import EstadoCargo, EstadoPagoCartera, TipoConceptoCartera
from app.schemas.cartera import CargoManualIn
from app.services.cartera import comun
from app.services.cartera import dominio as d
from app.services.cartera.pagos import aplicar_saldos_a_favor
from app.services.comun import Actor, NoEncontrado, ValidacionError, exigir, fijar_motivo, hoy_bogota


def _sumar_meses(f: date, n: int) -> date:
    mes = f.month - 1 + n
    anio, mes = f.year + mes // 12, mes % 12 + 1
    return date(anio, mes, min(f.day, calendar.monthrange(anio, mes)[1]))


def partir_en_cuotas(valor: Decimal, n: int, multiplo: int) -> list[Decimal]:
    """$1.000.000 en 3 cuotas con múltiplo 100 -> 333.300, 333.300, 333.400 (la última ajusta)."""
    if n == 1:
        return [valor]
    base = d.redondear(valor / n, multiplo)
    return [base] * (n - 1) + [valor - base * (n - 1)]


async def crear_cargos(db: AsyncSession, actor: Actor, data: CargoManualIn) -> list[CargoCartera]:
    exigir(actor, d.PUEDE_CARGAR, "crear cargos de cartera")
    concepto = await comun.concepto(db, actor, concepto_id=data.concepto_id)
    if not concepto.activo:
        raise ValidacionError(f"El concepto «{concepto.nombre}» está inactivo")
    if concepto.tipo in (TipoConceptoCartera.ORDINARIA, TipoConceptoCartera.INTERES):
        raise ValidacionError("La cuota ordinaria y los intereses se causan al facturar el periodo, no a mano")
    hoy = hoy_bogota()
    if data.primer_vencimiento < hoy:
        raise ValidacionError("El primer vencimiento no puede estar en el pasado")

    q = select(Unit).where(Unit.activa.is_(True))
    if not data.todas:
        q = q.where(Unit.id.in_(data.unidad_ids))
    unidades = list(await db.scalars(q))
    if not data.todas and len(unidades) != len(set(data.unidad_ids)):
        raise NoEncontrado("Alguna de las unidades no existe o está desactivada")
    cfg = await comun.config(db, actor)
    multiplo = cfg.redondeo if cfg else 100

    valores: dict[uuid.UUID, Decimal] = {}
    if data.modo == "TOTAL_POR_COEFICIENTE":
        con_coef = [u for u in unidades if u.coefficient]
        suma = sum((u.coefficient for u in con_coef if u.coefficient), Decimal(0))
        if not con_coef or suma <= 0:
            raise ValidacionError("Las unidades elegidas no tienen coeficiente para repartir el total")
        for u in con_coef:
            valores[u.id] = d.redondear(data.valor * (u.coefficient or 0) / suma, multiplo)
    else:
        valores = {u.id: data.valor for u in unidades}
    valores = {k: v for k, v in valores.items() if v > 0}
    if not valores:
        raise ValidacionError("No hay unidades a las que cobrar")

    await fijar_motivo(db, None)
    creados: list[CargoCartera] = []
    for unidad_id, total in valores.items():
        rid, rnombre = await comun.responsable(db, unidad_id)
        cuotas = partir_en_cuotas(total, data.numero_cuotas, multiplo)
        for i, valor in enumerate(cuotas):
            sufijo = f" (cuota {i + 1} de {len(cuotas)})" if len(cuotas) > 1 else ""
            c = CargoCartera(
                id=uuid.uuid4(),
                tenant_id=actor.tenant_id,
                unidad_id=unidad_id,
                concepto_id=concepto.id,
                descripcion=f"{data.descripcion}{sufijo}",
                valor=valor,
                fecha_causacion=hoy,
                fecha_vencimiento=_sumar_meses(data.primer_vencimiento, i),
                genera_interes=concepto.genera_interes,
                responsable_persona_id=rid,
                responsable_nombre=rnombre,
                creado_por_id=actor.user_id,
            )
            db.add(c)
            creados.append(c)
    await db.flush()
    for unidad_id in valores:
        await aplicar_saldos_a_favor(db, actor, unidad_id, hoy)
    return creados


async def anular_cargo(db: AsyncSession, actor: Actor, cargo_id: uuid.UUID, motivo: str) -> CargoCartera:
    exigir(actor, d.PUEDE_ANULAR, "anular cargos")
    c = await db.get(CargoCartera, cargo_id)
    if c is None or c.tenant_id != actor.tenant_id:
        raise NoEncontrado("Cargo no encontrado")
    if c.estado == EstadoCargo.ANULADO:
        raise ValidacionError("El cargo ya está anulado")
    pagado = await db.scalar(
        select(func.count())
        .select_from(AplicacionPago)
        .join(PagoCartera, PagoCartera.id == AplicacionPago.pago_id)
        .where(AplicacionPago.cargo_id == c.id, PagoCartera.estado == EstadoPagoCartera.APLICADO)
    )
    ajustado = await db.scalar(select(func.count()).select_from(AjusteCartera).where(AjusteCartera.cargo_id == c.id))
    if pagado or ajustado:
        raise ValidacionError(
            "El cargo tiene pagos o ajustes aplicados: anule primero esos pagos o corrija el valor con un ajuste"
        )
    await fijar_motivo(db, motivo)
    c.estado = EstadoCargo.ANULADO
    c.anulado_por_id = actor.user_id
    c.anulado_at = datetime.now(UTC)
    c.motivo_anulacion = motivo
    await db.flush()
    await fijar_motivo(db, None)
    return c
