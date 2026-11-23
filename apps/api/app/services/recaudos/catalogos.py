"""Catálogos del módulo: conceptos de recaudo, zonas sociales, reservas, personal y unidades."""

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ConceptoRecaudo, Membership, Reserva, Unit, User, ZonaSocial
from app.models.enums import EstadoReserva, TipoCobro, UserRole
from app.schemas.recaudos import (
    ConceptoCreate,
    ConceptoUpdate,
    ReservaCreate,
    ReservaUpdate,
    ZonaCreate,
    ZonaUpdate,
)
from app.services.recaudos.dominio import (
    PUEDE_GESTIONAR_CATALOGOS,
    PUEDE_REGISTRAR,
    Actor,
    NoEncontrado,
    R,
    ValidacionError,
    exigir,
)

PUEDE_VER_CATALOGOS = frozenset({R.ADMIN, R.AUXILIAR, R.CONTABILIDAD})


# --- Conceptos -----------------------------------------------------------------


async def listar_conceptos(db: AsyncSession, actor: Actor, *, incluir_inactivos: bool = False) -> list[ConceptoRecaudo]:
    exigir(actor, PUEDE_VER_CATALOGOS, "consultar los conceptos")
    q = select(ConceptoRecaudo).order_by(ConceptoRecaudo.nombre)
    if not incluir_inactivos:
        q = q.where(ConceptoRecaudo.activo)
    return list(await db.scalars(q))


async def crear_concepto(db: AsyncSession, actor: Actor, data: ConceptoCreate) -> ConceptoRecaudo:
    exigir(actor, PUEDE_GESTIONAR_CATALOGOS, "crear conceptos")
    existe = await db.scalar(select(ConceptoRecaudo.id).where(ConceptoRecaudo.codigo == data.codigo))
    if existe:
        raise ValidacionError(f"Ya existe un concepto con el código {data.codigo}")
    concepto = ConceptoRecaudo(id=uuid.uuid4(), tenant_id=actor.tenant_id, **data.model_dump())
    db.add(concepto)
    await db.flush()
    return concepto


async def editar_concepto(
    db: AsyncSession, actor: Actor, concepto_id: uuid.UUID, data: ConceptoUpdate
) -> ConceptoRecaudo:
    exigir(actor, PUEDE_GESTIONAR_CATALOGOS, "editar conceptos")
    concepto = await db.get(ConceptoRecaudo, concepto_id)
    if concepto is None or concepto.tenant_id != actor.tenant_id:
        raise NoEncontrado("Concepto no encontrado")
    for campo, valor in data.model_dump(exclude_unset=True).items():
        setattr(concepto, campo, valor)
    # Coherencia con los CHECK de la tabla, con mensaje claro
    if concepto.tipo_cobro == TipoCobro.POR_HORA and (concepto.tarifa_base is None or not concepto.fraccion_minutos):
        raise ValidacionError("Un cobro por hora necesita tarifa y fracción en minutos")
    if concepto.tipo_cobro == TipoCobro.FIJO and concepto.tarifa_base is None:
        raise ValidacionError("Un cobro fijo necesita tarifa")
    await db.flush()
    return concepto


# --- Zonas sociales ------------------------------------------------------------


async def listar_zonas(db: AsyncSession, actor: Actor, *, incluir_inactivas: bool = False) -> list[ZonaSocial]:
    exigir(actor, PUEDE_VER_CATALOGOS, "consultar las zonas sociales")
    q = select(ZonaSocial).order_by(ZonaSocial.nombre)
    if not incluir_inactivas:
        q = q.where(ZonaSocial.activo)
    return list(await db.scalars(q))


async def crear_zona(db: AsyncSession, actor: Actor, data: ZonaCreate) -> ZonaSocial:
    exigir(actor, PUEDE_GESTIONAR_CATALOGOS, "crear zonas sociales")
    zona = ZonaSocial(id=uuid.uuid4(), tenant_id=actor.tenant_id, **data.model_dump())
    db.add(zona)
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError as exc:
        raise ValidacionError(f"Ya existe una zona llamada «{data.nombre}»") from exc
    return zona


async def editar_zona(db: AsyncSession, actor: Actor, zona_id: uuid.UUID, data: ZonaUpdate) -> ZonaSocial:
    exigir(actor, PUEDE_GESTIONAR_CATALOGOS, "editar zonas sociales")
    zona = await db.get(ZonaSocial, zona_id)
    if zona is None or zona.tenant_id != actor.tenant_id:
        raise NoEncontrado("Zona no encontrada")
    for campo, valor in data.model_dump(exclude_unset=True).items():
        setattr(zona, campo, valor)
    await db.flush()
    return zona


# --- Reservas ----------------------------------------------------------------------


async def listar_reservas(
    db: AsyncSession, actor: Actor, *, desde: date | None = None, hasta: date | None = None
) -> list[Reserva]:
    exigir(actor, PUEDE_VER_CATALOGOS, "consultar las reservas")
    q = select(Reserva).order_by(Reserva.fecha_evento, Reserva.hora_inicio)
    if desde:
        q = q.where(Reserva.fecha_evento >= desde)
    if hasta:
        q = q.where(Reserva.fecha_evento <= hasta)
    return list(await db.scalars(q))


async def _validar_choque(db: AsyncSession, reserva: Reserva) -> None:
    """Dos reservas vigentes de la misma zona el mismo día no pueden cruzarse en horario.

    Sin horas definidas, la reserva ocupa el día completo.
    """
    q = select(Reserva.solicitante).where(
        Reserva.zona_id == reserva.zona_id,
        Reserva.fecha_evento == reserva.fecha_evento,
        Reserva.estado.in_([EstadoReserva.SOLICITADA, EstadoReserva.CONFIRMADA]),
        Reserva.id != reserva.id,
    )
    if reserva.hora_inicio and reserva.hora_fin:
        q = q.where(
            or_(
                Reserva.hora_inicio.is_(None),
                Reserva.hora_fin.is_(None),
                and_(Reserva.hora_inicio < reserva.hora_fin, Reserva.hora_fin > reserva.hora_inicio),
            )
        )
    if (otro := await db.scalar(q.limit(1))) is not None:
        raise ValidacionError(f"La zona ya está reservada en ese horario ({otro})")


async def crear_reserva(db: AsyncSession, actor: Actor, data: ReservaCreate) -> Reserva:
    exigir(actor, PUEDE_REGISTRAR, "crear reservas")
    zona = await db.get(ZonaSocial, data.zona_id)
    if zona is None or zona.tenant_id != actor.tenant_id or not zona.activo:
        raise NoEncontrado("Zona social no encontrada o inactiva")
    if data.unidad_id is not None:
        unidad = await db.get(Unit, data.unidad_id)
        if unidad is None or unidad.tenant_id != actor.tenant_id:
            raise NoEncontrado("Unidad no encontrada")
    reserva = Reserva(id=uuid.uuid4(), tenant_id=actor.tenant_id, creado_por_id=actor.user_id, **data.model_dump())
    await _validar_choque(db, reserva)
    db.add(reserva)
    await db.flush()
    return reserva


async def editar_reserva(db: AsyncSession, actor: Actor, reserva_id: uuid.UUID, data: ReservaUpdate) -> Reserva:
    exigir(actor, PUEDE_REGISTRAR, "editar reservas")
    reserva = await db.get(Reserva, reserva_id)
    if reserva is None or reserva.tenant_id != actor.tenant_id:
        raise NoEncontrado("Reserva no encontrada")
    if reserva.estado in (EstadoReserva.CANCELADA, EstadoReserva.REALIZADA):
        raise ValidacionError(f"Una reserva {reserva.estado.value.lower()} no se puede modificar")
    for campo, valor in data.model_dump(exclude_unset=True).items():
        setattr(reserva, campo, valor)
    if reserva.hora_inicio and reserva.hora_fin and reserva.hora_fin <= reserva.hora_inicio:
        raise ValidacionError("La hora de fin debe ser posterior a la de inicio")
    if reserva.estado in (EstadoReserva.SOLICITADA, EstadoReserva.CONFIRMADA):
        await _validar_choque(db, reserva)
    await db.flush()
    return reserva


# --- Personal y unidades (para los formularios) -----------------------------------


@dataclass(frozen=True)
class Persona:
    id: uuid.UUID
    nombre: str
    rol: UserRole


async def listar_personal(db: AsyncSession, actor: Actor, rol: UserRole | None = None) -> list[Persona]:
    """Miembros del personal (p. ej. los administradores que pueden recibir una entrega)."""
    exigir(actor, PUEDE_VER_CATALOGOS, "consultar el personal")
    q = (
        select(User.id, User.full_name, Membership.role)
        .join(Membership, Membership.user_id == User.id)
        .where(
            Membership.tenant_id == actor.tenant_id,
            User.is_active,
            Membership.role.in_([R.ADMIN, R.AUXILIAR, R.CONTABILIDAD]),
        )
        .order_by(User.full_name)
    )
    if rol is not None:
        q = q.where(Membership.role == rol)
    return [Persona(i, n, r) for i, n, r in await db.execute(q)]


async def listar_unidades(db: AsyncSession, actor: Actor) -> list[Unit]:
    exigir(actor, PUEDE_VER_CATALOGOS, "consultar las unidades")
    return list(await db.scalars(select(Unit).order_by(Unit.tower, Unit.number)))
