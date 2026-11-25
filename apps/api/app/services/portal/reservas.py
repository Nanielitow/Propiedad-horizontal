"""Reservas de zonas sociales hechas por el residente desde el portal.

Reglas por zona (horario, anticipación, cupo mensual por unidad, capacidad, exigir estar al
día con la cartera, aprobación manual o automática). El cruce de horarios lo valida el mismo
código de recaudos. El residente ve la disponibilidad sin saber quién reservó, y solo cancela.
El cobro del alquiler sigue siendo un recaudo asociado a la reserva (módulo de recaudos).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CarteraConfig, Reserva, Unit, User, ZonaSocial
from app.models.enums import EstadoReserva, UserRole
from app.schemas.portal import CancelarReservaIn, DecisionReservaIn, ReglasZonaIn, ReservaPortalIn
from app.services.cartera import comun as cartera
from app.services.comun import Actor, NoEncontrado, PermisoDenegado, ValidacionError, exigir, hoy_bogota, pesos
from app.services.portal import dominio as d
from app.services.recaudos.catalogos import _validar_choque

R = UserRole
ER = EstadoReserva
VIGENTES = (ER.SOLICITADA, ER.CONFIRMADA)


async def zona(db: AsyncSession, actor: Actor, zona_id: uuid.UUID) -> ZonaSocial:
    z = await db.get(ZonaSocial, zona_id)
    if z is None or z.tenant_id != actor.tenant_id:
        raise NoEncontrado("Zona social no encontrada")
    return z


def reglas(z: ZonaSocial) -> d.ReglasZona:
    return d.ReglasZona(
        z.hora_apertura,
        z.hora_cierre,
        z.anticipacion_min_dias,
        z.anticipacion_max_dias,
        z.max_reservas_mes_unidad,
        z.capacidad,
    )


async def configurar_zona(db: AsyncSession, actor: Actor, zona_id: uuid.UUID, data: ReglasZonaIn) -> ZonaSocial:
    exigir(actor, d.PUEDE_CONFIGURAR_ZONAS, "configurar las zonas sociales")
    z = await zona(db, actor, zona_id)
    cambios = data.model_dump(exclude_unset=True)
    for k, v in cambios.items():
        if v is None and k in ("hora_apertura", "hora_cierre", "anticipacion_min_dias", "anticipacion_max_dias",
                               "max_reservas_mes_unidad", "requiere_paz_y_salvo", "requiere_aprobacion", "reservable_residentes"):  # fmt: skip
            continue
        setattr(z, k, v)
    if z.hora_cierre <= z.hora_apertura:
        raise ValidacionError("La hora de cierre debe ser posterior a la de apertura")
    if z.anticipacion_max_dias <= z.anticipacion_min_dias:
        raise ValidacionError("La anticipación máxima debe ser mayor que la mínima")
    await db.flush()
    return z


@dataclass(frozen=True)
class Ocupado:
    fecha_evento: date
    hora_inicio: time | None
    hora_fin: time | None
    propia: bool


async def disponibilidad(db: AsyncSession, actor: Actor, zona_id: uuid.UUID, desde: date, hasta: date) -> list[Ocupado]:
    await zona(db, actor, zona_id)  # al residente la RLS no le muestra zonas no reservables
    if (hasta - desde).days > 120:
        raise ValidacionError("Consulte como máximo 120 días")
    filas = await db.execute(
        text("SELECT fecha_evento, hora_inicio, hora_fin, propia FROM disponibilidad_zona(:z, :d, :h)"),
        {"z": zona_id, "d": desde, "h": hasta},
    )
    return [Ocupado(*f) for f in filas.all()]


async def _verificar_paz_y_salvo(db: AsyncSession, actor: Actor, unidad_id: uuid.UUID) -> None:
    if await db.get(CarteraConfig, actor.tenant_id) is None:
        return  # la copropiedad no lleva la cartera en la plataforma
    vencido = await cartera.saldo_unidad(db, unidad_id, vencido_a=hoy_bogota())
    if vencido > 0:
        raise ValidacionError(
            f"Para reservar esta zona la unidad debe estar al día: tiene un saldo vencido de {pesos(vencido)}"
        )


async def solicitar(db: AsyncSession, actor: Actor, data: ReservaPortalIn) -> Reserva:
    """El residente reserva para una de sus unidades. Queda SOLICITADA o, si la zona no exige
    aprobación, CONFIRMADA de inmediato."""
    if actor.role != R.RESIDENTE:
        raise PermisoDenegado("Desde el portal reservan los residentes; el personal usa Recaudos → Reservas")
    z = await zona(db, actor, data.zona_id)
    if not z.activo or not z.reservable_residentes:
        raise ValidacionError("Esta zona no se reserva desde el portal")
    u = await db.get(Unit, data.unidad_id)  # RLS: solo sus unidades
    if u is None or u.tenant_id != actor.tenant_id:
        raise NoEncontrado("Unidad no encontrada")
    inicio_mes = data.fecha_evento.replace(day=1)
    del_mes = await db.scalar(
        select(func.count())
        .select_from(Reserva)
        .where(
            Reserva.unidad_id == u.id,
            Reserva.zona_id == z.id,
            Reserva.estado.in_(VIGENTES),
            Reserva.fecha_evento >= inicio_mes,
            Reserva.fecha_evento
            < (
                inicio_mes.replace(year=inicio_mes.year + 1, month=1)
                if inicio_mes.month == 12
                else inicio_mes.replace(month=inicio_mes.month + 1)
            ),
        )
    )
    errores = d.validar_reserva(
        reglas(z),
        hoy=hoy_bogota(),
        fecha=data.fecha_evento,
        hora_inicio=data.hora_inicio,
        hora_fin=data.hora_fin,
        asistentes=data.numero_asistentes,
        reservas_del_mes=del_mes or 0,
    )
    if errores:
        raise ValidacionError(". ".join(errores))
    if z.requiere_paz_y_salvo:
        await _verificar_paz_y_salvo(db, actor, u.id)
    usuario = await db.get(User, actor.user_id)
    r = Reserva(
        id=uuid.uuid4(),
        tenant_id=actor.tenant_id,
        zona_id=z.id,
        unidad_id=u.id,
        solicitante=(usuario.full_name.split(" (")[0] if usuario else "Residente")[:200],
        fecha_evento=data.fecha_evento,
        hora_inicio=data.hora_inicio,
        hora_fin=data.hora_fin,
        numero_asistentes=data.numero_asistentes,
        observaciones=data.observaciones,
        estado=ER.SOLICITADA if z.requiere_aprobacion else ER.CONFIRMADA,
        solicitada_en_portal=True,
        creado_por_id=actor.user_id,
    )
    # El cruce se valida con disponibilidad_zona (SECURITY DEFINER): al residente la RLS solo le
    # muestra SUS reservas, y una consulta directa no vería las de los vecinos.
    for o in await disponibilidad(db, actor, z.id, data.fecha_evento, data.fecha_evento):
        if (
            o.hora_inicio is None
            or o.hora_fin is None
            or (o.hora_inicio < data.hora_fin and o.hora_fin > data.hora_inicio)
        ):
            franja = f"de {o.hora_inicio:%H:%M} a {o.hora_fin:%H:%M}" if o.hora_inicio and o.hora_fin else "todo el día"
            raise ValidacionError(f"La zona ya está reservada ese día {franja}")
    db.add(r)
    await db.flush()
    return r


async def _reserva(db: AsyncSession, actor: Actor, reserva_id: uuid.UUID) -> Reserva:
    r = await db.get(Reserva, reserva_id)
    if r is None or r.tenant_id != actor.tenant_id:
        raise NoEncontrado("Reserva no encontrada")
    return r


async def cancelar(db: AsyncSession, actor: Actor, reserva_id: uuid.UUID, data: CancelarReservaIn) -> Reserva:
    r = await _reserva(db, actor, reserva_id)
    if actor.role not in (R.RESIDENTE, *d.PUEDE_DECIDIR_RESERVA):
        raise PermisoDenegado("Su rol no cancela reservas")
    if r.estado not in VIGENTES:
        raise ValidacionError(f"La reserva ya está {r.estado.value.lower()}")
    if actor.role == R.RESIDENTE and r.fecha_evento < hoy_bogota():
        raise ValidacionError("La fecha del evento ya pasó")
    r.estado = ER.CANCELADA
    r.motivo_decision = data.motivo
    r.decidida_por_id = actor.user_id
    r.decidida_at = datetime.now(UTC)
    await db.flush()
    return r


async def decidir(db: AsyncSession, actor: Actor, reserva_id: uuid.UUID, data: DecisionReservaIn) -> Reserva:
    """La administración aprueba o rechaza una solicitud hecha desde el portal."""
    exigir(actor, d.PUEDE_DECIDIR_RESERVA, "aprobar o rechazar reservas")
    r = await _reserva(db, actor, reserva_id)
    if r.estado != ER.SOLICITADA:
        raise ValidacionError(f"La reserva está {r.estado.value.lower()}: solo se deciden las solicitadas")
    if data.aprobar:
        await _validar_choque(db, r)
    r.estado = ER.CONFIRMADA if data.aprobar else ER.RECHAZADA
    r.motivo_decision = data.motivo
    r.decidida_por_id = actor.user_id
    r.decidida_at = datetime.now(UTC)
    await db.flush()
    return r


async def listar(
    db: AsyncSession,
    actor: Actor,
    *,
    estado: EstadoReserva | None = None,
    desde: date | None = None,
    hasta: date | None = None,
) -> list[Reserva]:
    """Personal: todas (para decidir y planear). Residente: las de sus unidades (RLS)."""
    if actor.role not in (R.RESIDENTE, R.ADMIN, R.AUXILIAR, R.CONTABILIDAD, R.CONSEJO):
        raise PermisoDenegado("Su rol no consulta reservas")
    q = select(Reserva).order_by(Reserva.fecha_evento, Reserva.hora_inicio)
    if estado:
        q = q.where(Reserva.estado == estado)
    if desde:
        q = q.where(Reserva.fecha_evento >= desde)
    if hasta:
        q = q.where(Reserva.fecha_evento <= hasta)
    return list(await db.scalars(q))
