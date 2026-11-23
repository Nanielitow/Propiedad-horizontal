"""Control de efectivo: cierre de caja por turno y entregas internas.

Flujo del efectivo:
  recaudo en EFECTIVO -> cierre de caja del receptor (se cuenta el dinero)
  -> entrega interna a la administración (opcional) -> consignación bancaria.

Todo efectivo pasa por un cierre antes de entregarse o consignarse: así cada
peso queda contado por alguien con nombre propio.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AlertaRecaudo,
    CierreCaja,
    Consignacion,
    ConsignacionRecaudo,
    EntregaInterna,
    Membership,
    Recaudo,
    User,
)
from app.models.enums import (
    EstadoConsignacion,
    EstadoEntrega,
    EstadoRecaudo,
    MedioPago,
    SeveridadAlerta,
    TipoAlerta,
    UserRole,
)
from app.schemas.recaudos import CierreCajaIn, EntregaConfirmacion, EntregaCreate
from app.services.recaudos.alertas import crear_alerta
from app.services.recaudos.dominio import (
    PUEDE_CERRAR_CAJA,
    PUEDE_ENTREGAR,
    PUEDE_RECIBIR_ENTREGA,
    Actor,
    NoEncontrado,
    PermisoDenegado,
    TransicionInvalida,
    ValidacionError,
    exigir,
    pesos,
)
from app.services.recaudos.service import _motivo

E = EstadoRecaudo


@dataclass
class ResumenCaja:
    inicio_turno: datetime
    recaudos: list[Recaudo]
    total_efectivo: Decimal

    @property
    def cantidad(self) -> int:
        return len(self.recaudos)


def _efectivo_abierto(usuario_id: uuid.UUID):  # type: ignore[no-untyped-def]
    """Efectivo recibido por el usuario que aún no está en ningún cierre (los anulados no cuentan)."""
    return (
        select(Recaudo)
        .where(
            Recaudo.usuario_receptor_id == usuario_id,
            Recaudo.medio_pago == MedioPago.EFECTIVO,
            Recaudo.cierre_id.is_(None),
            Recaudo.estado != E.ANULADO,
        )
        .order_by(Recaudo.fecha_recaudo, Recaudo.consecutivo)
    )


async def _inicio_turno(db: AsyncSession, actor: Actor, recaudos: list[Recaudo], ahora: datetime) -> datetime:
    ultimo_cierre = await db.scalar(
        select(func.max(CierreCaja.fin_turno)).where(CierreCaja.usuario_id == actor.user_id)
    )
    if ultimo_cierre is not None:
        return ultimo_cierre
    return recaudos[0].fecha_recaudo if recaudos else ahora


async def estado_caja(db: AsyncSession, actor: Actor, *, ahora: datetime | None = None) -> ResumenCaja:
    """Vista previa del cierre: lo que el sistema espera encontrar en la caja del usuario."""
    exigir(actor, PUEDE_CERRAR_CAJA, "consultar la caja")
    ahora = ahora or datetime.now(UTC)
    recaudos = list(await db.scalars(_efectivo_abierto(actor.user_id)))
    total = sum((r.valor_recibido for r in recaudos), Decimal(0))
    return ResumenCaja(await _inicio_turno(db, actor, recaudos, ahora), recaudos, total)


async def cerrar_caja(
    db: AsyncSession, actor: Actor, data: CierreCajaIn, *, ahora: datetime | None = None
) -> tuple[CierreCaja, list[AlertaRecaudo]]:
    exigir(actor, PUEDE_CERRAR_CAJA, "cerrar la caja")
    ahora = ahora or datetime.now(UTC)
    # FOR UPDATE: dos cierres simultáneos del mismo usuario no pueden contar el mismo dinero
    recaudos = list(await db.scalars(_efectivo_abierto(actor.user_id).with_for_update()))
    esperado = data.saldo_inicial + sum((r.valor_recibido for r in recaudos), Decimal(0))
    diferencia = data.valor_fisico_contado - esperado
    justificacion = (data.observacion_justificacion or "").strip() or None
    if diferencia != 0 and (justificacion is None or len(justificacion) < 10):
        tipo = "sobrante" if diferencia > 0 else "faltante"
        raise ValidacionError(
            f"Hay un {tipo} de {pesos(abs(diferencia))}: escriba una justificación de al menos 10 caracteres"
        )

    cierre = CierreCaja(
        id=uuid.uuid4(),
        tenant_id=actor.tenant_id,
        usuario_id=actor.user_id,
        inicio_turno=await _inicio_turno(db, actor, recaudos, ahora),
        fin_turno=ahora,
        saldo_inicial=data.saldo_inicial,
        saldo_esperado_sistema=esperado,
        valor_fisico_contado=data.valor_fisico_contado,
        observacion_justificacion=justificacion,
    )
    db.add(cierre)
    await db.flush()
    await _motivo(db, f"Cierre de caja #{cierre.consecutivo}")
    for r in recaudos:
        r.cierre_id = cierre.id
    await db.flush()
    await _motivo(db, None)

    alertas = []
    if diferencia != 0:
        usuario = await db.get(User, actor.user_id)
        nombre = usuario.full_name if usuario else "usuario"
        faltante = diferencia < 0
        alertas.append(
            await crear_alerta(
                db,
                actor.tenant_id,
                tipo=TipoAlerta.DIFERENCIA_CIERRE,
                severidad=SeveridadAlerta.CRITICA if faltante else SeveridadAlerta.ADVERTENCIA,
                entidad="cierre_caja",
                entidad_id=cierre.id,
                mensaje=(
                    f"Cierre de caja #{cierre.consecutivo} de {nombre}: "
                    f"{'faltante' if faltante else 'sobrante'} de {pesos(abs(diferencia))} "
                    f"(esperado {pesos(esperado)}, contado {pesos(data.valor_fisico_contado)}). "
                    f"Justificación: {justificacion}"
                ),
                monto=abs(diferencia),
            )
        )
    return cierre, alertas


# --- Entregas internas -----------------------------------------------------------


async def _consignado_vigente(db: AsyncSession, recaudo_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    """Recaudos con dinero aplicado a alguna consignación no rechazada."""
    rows = await db.scalars(
        select(ConsignacionRecaudo.recaudo_id)
        .join(Consignacion, Consignacion.id == ConsignacionRecaudo.consignacion_id)
        .where(ConsignacionRecaudo.recaudo_id.in_(recaudo_ids), Consignacion.estado != EstadoConsignacion.RECHAZADA)
    )
    return set(rows)


async def crear_entrega(db: AsyncSession, actor: Actor, data: EntregaCreate) -> EntregaInterna:
    exigir(actor, PUEDE_ENTREGAR, "entregar efectivo")
    if data.recibido_por_id == actor.user_id:
        raise ValidacionError("No puede entregarse el efectivo a sí mismo")
    receptor = await db.scalar(
        select(Membership.id).where(
            Membership.tenant_id == actor.tenant_id,
            Membership.user_id == data.recibido_por_id,
            Membership.role == UserRole.ADMIN,
        )
    )
    if receptor is None:
        raise ValidacionError("Quien recibe debe ser un administrador de la copropiedad")

    recaudos = list(await db.scalars(select(Recaudo).where(Recaudo.id.in_(data.recaudo_ids)).with_for_update()))
    if len(recaudos) != len(data.recaudo_ids):
        raise NoEncontrado("Algún recaudo no existe o no le pertenece")
    for r in recaudos:
        if r.usuario_receptor_id != actor.user_id:
            raise PermisoDenegado(f"El recaudo #{r.consecutivo} lo recibió otra persona")
        if r.medio_pago != MedioPago.EFECTIVO or r.estado != E.RECAUDADO_EN_CAJA:
            raise ValidacionError(f"El recaudo #{r.consecutivo} no es efectivo en caja")
        if r.cierre_id is None:
            raise ValidacionError(f"El recaudo #{r.consecutivo} aún no está en un cierre de caja: cierre primero")
        if r.entrega_id is not None:
            raise ValidacionError(f"El recaudo #{r.consecutivo} ya tiene una entrega en curso")
    if consignados := await _consignado_vigente(db, data.recaudo_ids):
        numeros = sorted(r.consecutivo for r in recaudos if r.id in consignados)
        raise ValidacionError(f"Recaudos ya incluidos en una consignación: {', '.join(f'#{n}' for n in numeros)}")

    entrega = EntregaInterna(
        id=uuid.uuid4(),
        tenant_id=actor.tenant_id,
        entregado_por_id=actor.user_id,
        recibido_por_id=data.recibido_por_id,
        valor_total=sum((r.valor_recibido for r in recaudos), Decimal(0)),
        observaciones=data.observaciones,
    )
    db.add(entrega)
    await db.flush()
    await _motivo(db, f"Entrega interna #{entrega.consecutivo}")
    for r in recaudos:
        r.entrega_id = entrega.id
    await db.flush()
    await _motivo(db, None)
    return entrega


async def _entrega_pendiente_para(db: AsyncSession, actor: Actor, entrega_id: uuid.UUID) -> EntregaInterna:
    exigir(actor, PUEDE_RECIBIR_ENTREGA, "recibir entregas de efectivo")
    entrega = await db.get(EntregaInterna, entrega_id, with_for_update=True)
    if entrega is None or entrega.tenant_id != actor.tenant_id:
        raise NoEncontrado("Entrega no encontrada")
    if entrega.recibido_por_id != actor.user_id:
        raise PermisoDenegado("Solo quien recibe el efectivo puede confirmar o rechazar la entrega")
    if entrega.estado != EstadoEntrega.PENDIENTE_CONFIRMACION:
        raise TransicionInvalida(f"La entrega ya está {entrega.estado.value.lower()}")
    return entrega


async def confirmar_entrega(
    db: AsyncSession, actor: Actor, entrega_id: uuid.UUID, data: EntregaConfirmacion, *, ahora: datetime | None = None
) -> tuple[EntregaInterna, list[AlertaRecaudo]]:
    entrega = await _entrega_pendiente_para(db, actor, entrega_id)
    diferencia = data.valor_contado - entrega.valor_total
    nota = (data.observaciones or "").strip()
    if diferencia != 0 and len(nota) < 10:
        raise ValidacionError(
            f"El valor contado difiere en {pesos(abs(diferencia))}: explique la diferencia (mínimo 10 caracteres)"
        )

    await _motivo(db, f"Confirmación de la entrega #{entrega.consecutivo}")
    entrega.estado = EstadoEntrega.CONFIRMADA
    entrega.valor_contado = data.valor_contado
    entrega.confirmada_at = ahora or datetime.now(UTC)
    if nota:
        entrega.observaciones = "\n".join(filter(None, [entrega.observaciones, f"Al recibir: {nota}"]))
    for r in await db.scalars(select(Recaudo).where(Recaudo.entrega_id == entrega.id)):
        if r.estado == E.RECAUDADO_EN_CAJA:  # un recaudo anulado mientras tanto no cambia
            r.estado = E.ENTREGADO_ADMINISTRACION
    await db.flush()
    await _motivo(db, None)

    alertas = []
    if diferencia != 0:
        alertas.append(
            await crear_alerta(
                db,
                actor.tenant_id,
                tipo=TipoAlerta.DESCUADRE_ENTREGA,
                severidad=SeveridadAlerta.CRITICA if diferencia < 0 else SeveridadAlerta.ADVERTENCIA,
                entidad="entrega_interna",
                entidad_id=entrega.id,
                mensaje=(
                    f"Entrega interna #{entrega.consecutivo}: se esperaban {pesos(entrega.valor_total)} y se "
                    f"contaron {pesos(data.valor_contado)}. Nota: {nota}"
                ),
                monto=abs(diferencia),
            )
        )
    return entrega, alertas


async def rechazar_entrega(db: AsyncSession, actor: Actor, entrega_id: uuid.UUID, motivo: str) -> EntregaInterna:
    """El efectivo vuelve a la caja de quien lo entregó (los recaudos quedan libres para otra entrega)."""
    entrega = await _entrega_pendiente_para(db, actor, entrega_id)
    motivo = motivo.strip()
    if len(motivo) < 10:
        raise ValidacionError("El motivo del rechazo debe tener al menos 10 caracteres")
    await _motivo(db, motivo)
    entrega.estado = EstadoEntrega.RECHAZADA
    entrega.observaciones = "\n".join(filter(None, [entrega.observaciones, f"Rechazada: {motivo}"]))
    for r in await db.scalars(select(Recaudo).where(Recaudo.entrega_id == entrega.id)):
        if r.estado == E.RECAUDADO_EN_CAJA:
            r.entrega_id = None
    await db.flush()
    await _motivo(db, None)
    return entrega
