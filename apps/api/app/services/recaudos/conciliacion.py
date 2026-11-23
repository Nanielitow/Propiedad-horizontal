"""Conciliación bancaria: consignaciones que agrupan efectivo, también por partes.

Ciclo de una consignación:
  REGISTRADA (con soporte) -> APROBADA (admin o contabilidad) -> VERIFICADA (cruzada con el extracto)
  REGISTRADA -> RECHAZADA (libera el saldo aplicado)

Un recaudo pasa a CONSIGNADO cuando TODO su valor está aplicado en consignaciones
aprobadas, y a VERIFICADO cuando todas ellas están verificadas.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AlertaRecaudo, Consignacion, ConsignacionRecaudo, EntregaInterna, Recaudo
from app.models.enums import EstadoConsignacion, EstadoEntrega, EstadoRecaudo, MedioPago, SeveridadAlerta, TipoAlerta
from app.schemas.recaudos import ConsignacionCreate
from app.services.recaudos.alertas import crear_alerta
from app.services.recaudos.dominio import (
    PUEDE_APROBAR_CONSIGNACION,
    PUEDE_CONSIGNAR,
    Actor,
    NoEncontrado,
    TransicionInvalida,
    ValidacionError,
    exigir,
    pesos,
    validar_soporte,
)
from app.services.recaudos.service import _motivo

E = EstadoRecaudo
C = EstadoConsignacion
TZ = ZoneInfo("America/Bogota")
_CONSIGNABLE = (E.RECAUDADO_EN_CAJA, E.ENTREGADO_ADMINISTRACION)


@dataclass
class Cobertura:
    """Cuánto de un recaudo está aplicado, según el estado de sus consignaciones."""

    registrado: Decimal = Decimal(0)
    aprobado: Decimal = Decimal(0)
    verificado: Decimal = Decimal(0)

    @property
    def vigente(self) -> Decimal:  # todo lo no rechazado
        return self.registrado + self.aprobado + self.verificado


async def _coberturas(db: AsyncSession, recaudo_ids: list[uuid.UUID]) -> dict[uuid.UUID, Cobertura]:
    rows = await db.execute(
        select(ConsignacionRecaudo.recaudo_id, Consignacion.estado, func.sum(ConsignacionRecaudo.valor_aplicado))
        .join(Consignacion, Consignacion.id == ConsignacionRecaudo.consignacion_id)
        .where(ConsignacionRecaudo.recaudo_id.in_(recaudo_ids), Consignacion.estado != C.RECHAZADA)
        .group_by(ConsignacionRecaudo.recaudo_id, Consignacion.estado)
    )
    cob: dict[uuid.UUID, Cobertura] = defaultdict(Cobertura)
    for recaudo_id, estado, suma in rows:
        campo = {C.REGISTRADA: "registrado", C.APROBADA: "aprobado", C.VERIFICADA: "verificado"}[estado]
        setattr(cob[recaudo_id], campo, suma)
    return cob


@dataclass
class Pendiente:
    recaudo: Recaudo
    saldo: Decimal


async def pendientes_por_consignar(db: AsyncSession, actor: Actor) -> list[Pendiente]:
    """Efectivo ya cerrado en caja con saldo sin consignar (el auxiliar solo ve el suyo, por RLS)."""
    exigir(actor, PUEDE_CONSIGNAR, "consultar el efectivo por consignar")
    recaudos = list(
        await db.scalars(
            select(Recaudo)
            .where(
                Recaudo.medio_pago == MedioPago.EFECTIVO,
                Recaudo.estado.in_(_CONSIGNABLE),
                Recaudo.cierre_id.is_not(None),
            )
            .order_by(Recaudo.fecha_recaudo, Recaudo.consecutivo)
        )
    )
    cob = await _coberturas(db, [r.id for r in recaudos])
    return [Pendiente(r, saldo) for r in recaudos if (saldo := r.valor_recibido - cob[r.id].vigente) > 0]


async def registrar_consignacion(
    db: AsyncSession, actor: Actor, data: ConsignacionCreate, *, ahora: datetime | None = None
) -> tuple[Consignacion, list[AlertaRecaudo]]:
    exigir(actor, PUEDE_CONSIGNAR, "registrar consignaciones")
    validar_soporte(actor, data.soporte_bancario_key)
    hoy = (ahora or datetime.now(UTC)).astimezone(TZ).date()
    if data.fecha_consignacion > hoy:
        raise ValidacionError("La fecha de la consignación no puede estar en el futuro")
    duplicada = await db.scalar(
        select(Consignacion.consecutivo).where(
            Consignacion.banco_destino == data.banco_destino,
            Consignacion.referencia_bancaria == data.referencia_bancaria,
        )
    )
    if duplicada is not None:
        raise ValidacionError(f"Esa referencia bancaria ya está registrada (consignación #{duplicada})")

    ids = [a.recaudo_id for a in data.aplicaciones]
    # FOR UPDATE: dos consignaciones simultáneas no pueden aplicar el mismo saldo
    recaudos = {r.id: r for r in await db.scalars(select(Recaudo).where(Recaudo.id.in_(ids)).with_for_update())}
    if len(recaudos) != len(ids):
        raise NoEncontrado("Algún recaudo no existe o no tiene acceso a él")
    entregas_pendientes = set(
        await db.scalars(
            select(EntregaInterna.id).where(
                EntregaInterna.id.in_([r.entrega_id for r in recaudos.values() if r.entrega_id]),
                EntregaInterna.estado == EstadoEntrega.PENDIENTE_CONFIRMACION,
            )
        )
    )
    cob = await _coberturas(db, ids)

    aplicaciones: list[tuple[Recaudo, Decimal]] = []
    for a in data.aplicaciones:
        r = recaudos[a.recaudo_id]
        if r.medio_pago != MedioPago.EFECTIVO or r.estado not in _CONSIGNABLE:
            raise ValidacionError(f"El recaudo #{r.consecutivo} no es efectivo pendiente de consignar")
        if r.cierre_id is None:
            raise ValidacionError(f"El recaudo #{r.consecutivo} aún no está en un cierre de caja")
        if r.entrega_id in entregas_pendientes:
            raise ValidacionError(f"El recaudo #{r.consecutivo} tiene una entrega interna sin confirmar")
        saldo = r.valor_recibido - cob[r.id].vigente
        valor = a.valor_aplicado if a.valor_aplicado is not None else saldo
        if saldo <= 0:
            raise ValidacionError(f"El recaudo #{r.consecutivo} ya está consignado en su totalidad")
        if valor > saldo:
            raise ValidacionError(f"Al recaudo #{r.consecutivo} solo le quedan {pesos(saldo)} por consignar")
        aplicaciones.append((r, valor))

    consignacion = Consignacion(
        id=uuid.uuid4(),
        tenant_id=actor.tenant_id,
        fecha_consignacion=data.fecha_consignacion,
        banco_destino=data.banco_destino,
        referencia_bancaria=data.referencia_bancaria,
        valor_consignado=data.valor_consignado,
        soporte_bancario_key=data.soporte_bancario_key,
        usuario_consigna_id=actor.user_id,
        observaciones=data.observaciones,
    )
    db.add(consignacion)
    await db.flush()
    db.add_all(
        ConsignacionRecaudo(
            consignacion_id=consignacion.id, recaudo_id=r.id, tenant_id=actor.tenant_id, valor_aplicado=valor
        )
        for r, valor in aplicaciones
    )
    await db.flush()

    alertas = []
    aplicado = sum((v for _, v in aplicaciones), Decimal(0))
    if aplicado != data.valor_consignado:
        alertas.append(
            await crear_alerta(
                db,
                actor.tenant_id,
                tipo=TipoAlerta.DESCUADRE_CONSIGNACION,
                severidad=SeveridadAlerta.CRITICA if data.valor_consignado < aplicado else SeveridadAlerta.ADVERTENCIA,
                entidad="consignacion",
                entidad_id=consignacion.id,
                mensaje=(
                    f"Consignación #{consignacion.consecutivo} ({data.banco_destino}, ref. {data.referencia_bancaria}): "
                    f"el banco recibió {pesos(data.valor_consignado)} pero los recaudos asociados suman {pesos(aplicado)}."
                ),
                monto=abs(data.valor_consignado - aplicado),
            )
        )
    return consignacion, alertas


async def _consignacion(
    db: AsyncSession, actor: Actor, consignacion_id: uuid.UUID, esperado: EstadoConsignacion
) -> Consignacion:
    exigir(actor, PUEDE_APROBAR_CONSIGNACION, "aprobar, verificar o rechazar consignaciones")
    c = await db.get(Consignacion, consignacion_id, with_for_update=True)
    if c is None or c.tenant_id != actor.tenant_id:
        raise NoEncontrado("Consignación no encontrada")
    if c.estado != esperado:
        raise TransicionInvalida(f"La consignación está {c.estado.value.lower()}; se esperaba {esperado.value.lower()}")
    return c


async def _recaudos_de(db: AsyncSession, consignacion_id: uuid.UUID) -> list[Recaudo]:
    return list(
        await db.scalars(
            select(Recaudo)
            .join(ConsignacionRecaudo, ConsignacionRecaudo.recaudo_id == Recaudo.id)
            .where(ConsignacionRecaudo.consignacion_id == consignacion_id)
            .with_for_update(of=Recaudo)
        )
    )


async def aprobar_consignacion(
    db: AsyncSession, actor: Actor, consignacion_id: uuid.UUID, *, ahora: datetime | None = None
) -> tuple[Consignacion, list[Recaudo]]:
    """Devuelve la consignación y los recaudos que quedaron CONSIGNADOS (cubiertos al 100 %)."""
    c = await _consignacion(db, actor, consignacion_id, C.REGISTRADA)
    await _motivo(db, f"Aprobación de la consignación #{c.consecutivo}")
    c.estado = C.APROBADA
    c.aprobada_por_id = actor.user_id
    c.aprobada_at = ahora or datetime.now(UTC)
    await db.flush()

    recaudos = await _recaudos_de(db, c.id)
    cob = await _coberturas(db, [r.id for r in recaudos])
    consignados = []
    for r in recaudos:
        if r.estado in _CONSIGNABLE and cob[r.id].aprobado + cob[r.id].verificado == r.valor_recibido:
            r.estado = E.CONSIGNADO
            consignados.append(r)
    await db.flush()
    await _motivo(db, None)
    return c, consignados


async def verificar_consignacion(
    db: AsyncSession, actor: Actor, consignacion_id: uuid.UUID, *, ahora: datetime | None = None
) -> tuple[Consignacion, list[Recaudo]]:
    """Cruzada con el extracto. Devuelve los recaudos que quedaron VERIFICADOS."""
    ahora = ahora or datetime.now(UTC)
    c = await _consignacion(db, actor, consignacion_id, C.APROBADA)
    await _motivo(db, f"Verificación de la consignación #{c.consecutivo} contra el extracto")
    c.estado = C.VERIFICADA
    c.verificada_por_id = actor.user_id
    c.verificada_at = ahora
    await db.flush()

    recaudos = await _recaudos_de(db, c.id)
    cob = await _coberturas(db, [r.id for r in recaudos])
    verificados = []
    for r in recaudos:
        if r.estado == E.CONSIGNADO and cob[r.id].verificado == r.valor_recibido:
            r.estado = E.VERIFICADO
            r.verificado_por_id = actor.user_id
            r.verificado_at = ahora
            verificados.append(r)
    await db.flush()
    await _motivo(db, None)
    return c, verificados


async def rechazar_consignacion(
    db: AsyncSession, actor: Actor, consignacion_id: uuid.UUID, motivo: str
) -> Consignacion:
    """Solo antes de aprobarla: el saldo aplicado vuelve a quedar pendiente por consignar."""
    motivo = motivo.strip()
    if len(motivo) < 10:
        raise ValidacionError("El motivo del rechazo debe tener al menos 10 caracteres")
    c = await _consignacion(db, actor, consignacion_id, C.REGISTRADA)
    await _motivo(db, motivo)
    c.estado = C.RECHAZADA
    c.observaciones = "\n".join(filter(None, [c.observaciones, f"Rechazada: {motivo}"]))
    await db.flush()
    await _motivo(db, None)
    return c
