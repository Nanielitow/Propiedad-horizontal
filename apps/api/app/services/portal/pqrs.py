"""PQRS: radicación (residente desde el portal o el personal a nombre de alguien), conversación
con notas internas, respuesta formal, asignación, cierre con calificación y conversión en
novedad de mantenimiento. La base impone el flujo de estados y que lo radicado no cambie."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Membership, Pqrs, PqrsMensaje, Unit, User
from app.models.enums import CategoriaPqrs, EstadoPqrs, PrioridadNovedad, PrioridadPqrs, UserRole
from app.schemas.activos import NovedadIn
from app.schemas.portal import (
    CalificacionIn,
    GestionPqrsIn,
    MensajeIn,
    NovedadDesdePqrsIn,
    PqrsIn,
    ReabrirIn,
    RespuestaIn,
)
from app.services.activos import novedades
from app.services.comun import Actor, NoEncontrado, PermisoDenegado, ValidacionError, exigir, hoy_bogota
from app.services.portal import adjuntos as adj
from app.services.portal import dominio as d

R = UserRole
E = EstadoPqrs


async def obtener(db: AsyncSession, actor: Actor, pqrs_id: uuid.UUID) -> Pqrs:
    p = await db.get(Pqrs, pqrs_id)  # la RLS decide quién la ve
    if p is None or p.tenant_id != actor.tenant_id:
        raise NoEncontrado("PQRS no encontrada")
    return p


def _es_autor(actor: Actor, p: Pqrs) -> bool:
    return p.radicado_por_id == actor.user_id


def _puede_gestionar(actor: Actor, p: Pqrs) -> bool:
    if actor.role in d.PUEDE_GESTIONAR_PQRS:
        return True
    if actor.role == R.CONTABILIDAD and p.categoria == CategoriaPqrs.CARTERA:
        return True
    return actor.role == R.MANTENIMIENTO and p.asignado_a_id == actor.user_id


async def radicar(db: AsyncSession, actor: Actor, data: PqrsIn) -> Pqrs:
    a_nombre = actor.role in d.PUEDE_RADICAR_A_NOMBRE
    if not a_nombre and actor.role != R.RESIDENTE:
        raise PermisoDenegado("Su rol no radica PQRS")
    if not a_nombre and (data.canal.value != "PORTAL" or data.solicitante_nombre or data.prioridad):
        raise PermisoDenegado("Desde el portal la PQRS se radica a su nombre")
    if data.unidad_id is not None:
        u = await db.get(Unit, data.unidad_id)  # al residente la RLS solo le muestra las suyas
        if u is None or u.tenant_id != actor.tenant_id:
            raise NoEncontrado("Unidad no encontrada")
    usuario = await db.get(User, actor.user_id)
    nombre = (
        data.solicitante_nombre
        if a_nombre and data.solicitante_nombre
        else (usuario.full_name.split(" (")[0] if usuario else "")
    )
    if a_nombre and data.canal.value != "PORTAL" and not data.solicitante_nombre:
        raise ValidacionError("Indique a nombre de quién se radica (PQRS presencial, por correo o teléfono)")
    p = Pqrs(
        id=uuid.uuid4(),
        tenant_id=actor.tenant_id,
        tipo=data.tipo,
        categoria=data.categoria,
        asunto=data.asunto,
        descripcion=data.descripcion,
        unidad_id=data.unidad_id,
        canal=data.canal,
        prioridad=data.prioridad or PrioridadPqrs.MEDIA,
        radicado_por_id=actor.user_id,
        solicitante_nombre=nombre,
        solicitante_contacto=data.solicitante_contacto if a_nombre else (usuario.email if usuario else None),
        fecha_limite=d.sumar_dias_habiles(hoy_bogota(), d.PLAZO_DIAS_HABILES),
        adjuntos=await adj.validar(actor, data.adjuntos),
    )
    db.add(p)
    await db.flush()
    return p


async def _mensaje(
    db: AsyncSession,
    actor: Actor,
    p: Pqrs,
    texto: str,
    *,
    interno: bool = False,
    respuesta: bool = False,
    adjuntos: list | None = None,
) -> PqrsMensaje:  # type: ignore[type-arg]
    m = PqrsMensaje(
        id=uuid.uuid4(),
        tenant_id=actor.tenant_id,
        pqrs_id=p.id,
        autor_id=actor.user_id,
        autor_rol=actor.role.value,
        texto=texto,
        interno=interno,
        es_respuesta=respuesta,
        adjuntos=adjuntos or [],
    )
    db.add(m)
    await db.flush()
    return m


async def comentar(db: AsyncSession, actor: Actor, pqrs_id: uuid.UUID, data: MensajeIn) -> PqrsMensaje:
    p = await obtener(db, actor, pqrs_id)
    if p.estado in (E.CERRADA, E.DESISTIDA):
        raise ValidacionError(f"La PQRS está {p.estado.value.lower()}: radique una nueva si hace falta")
    if data.interno and not _puede_gestionar(actor, p):
        raise PermisoDenegado("Solo el personal deja notas internas")
    if not _puede_gestionar(actor, p) and not _es_autor(actor, p):
        raise PermisoDenegado("Su rol solo puede consultar esta PQRS")
    m = await _mensaje(db, actor, p, data.texto, interno=data.interno, adjuntos=await adj.validar(actor, data.adjuntos))
    # La administración empieza a atenderla con su primer mensaje
    if _puede_gestionar(actor, p) and not data.interno and p.estado == E.RADICADA:
        p.estado = E.EN_TRAMITE
        await db.flush()
    return m


async def responder(db: AsyncSession, actor: Actor, pqrs_id: uuid.UUID, data: RespuestaIn) -> Pqrs:
    p = await obtener(db, actor, pqrs_id)
    if not _puede_gestionar(actor, p):
        raise PermisoDenegado("Su rol no responde PQRS")
    if p.estado not in d.ABIERTAS:
        raise ValidacionError(f"La PQRS ya está {p.estado.value.lower()}")
    await _mensaje(db, actor, p, data.texto, respuesta=True, adjuntos=await adj.validar(actor, data.adjuntos))
    p.estado = E.RESPONDIDA
    await db.flush()
    await db.refresh(p)
    return p


async def gestionar(db: AsyncSession, actor: Actor, pqrs_id: uuid.UUID, data: GestionPqrsIn) -> Pqrs:
    p = await obtener(db, actor, pqrs_id)
    if not _puede_gestionar(actor, p):
        raise PermisoDenegado("Su rol no gestiona esta PQRS")
    if data.estado is not None and data.estado != p.estado:
        if data.estado == E.RESPONDIDA:
            raise ValidacionError("Para responder use «Responder»: la respuesta queda escrita para el residente")
        if data.estado == E.CERRADA and actor.role not in d.PUEDE_GESTIONAR_PQRS:
            raise PermisoDenegado("Solo la administración cierra PQRS")
        if not d.puede_pasar(p.estado, data.estado):
            raise ValidacionError(f"No se puede pasar de {p.estado.value.lower()} a {data.estado.value.lower()}")
        p.estado = data.estado
    if data.asignado_a_id is not None or data.quitar_asignacion:
        if actor.role not in d.PUEDE_GESTIONAR_PQRS:
            raise PermisoDenegado("Solo la administración asigna PQRS")
        if data.asignado_a_id is not None:
            rol = await db.scalar(
                select(Membership.role).where(
                    Membership.tenant_id == actor.tenant_id, Membership.user_id == data.asignado_a_id
                )
            )
            if rol is None or rol == R.RESIDENTE:
                raise ValidacionError("Solo se puede asignar a alguien del personal de la copropiedad")
        p.asignado_a_id = None if data.quitar_asignacion else data.asignado_a_id
        if p.estado == E.RADICADA:
            p.estado = E.EN_TRAMITE
    if data.prioridad is not None:
        p.prioridad = data.prioridad
    if data.categoria is not None:
        p.categoria = data.categoria
    await db.flush()
    await db.refresh(p)
    return p


# --- Acciones del residente ------------------------------------------------------------------


async def calificar(db: AsyncSession, actor: Actor, pqrs_id: uuid.UUID, data: CalificacionIn) -> Pqrs:
    """El residente da por resuelta la respuesta: califica y la PQRS se cierra."""
    p = await obtener(db, actor, pqrs_id)
    if not _es_autor(actor, p):
        raise PermisoDenegado("Solo quien radicó la PQRS la califica")
    if p.estado not in (E.RESPONDIDA, E.CERRADA) or p.calificacion is not None:
        raise ValidacionError("Se califica una vez, cuando la PQRS ya tiene respuesta")
    p.calificacion = data.calificacion
    p.comentario_calificacion = data.comentario
    p.estado = E.CERRADA
    await db.flush()
    await db.refresh(p)
    return p


async def reabrir(db: AsyncSession, actor: Actor, pqrs_id: uuid.UUID, data: ReabrirIn) -> Pqrs:
    """La respuesta no resolvió: vuelve a trámite con la explicación del residente."""
    p = await obtener(db, actor, pqrs_id)
    if not _es_autor(actor, p):
        raise PermisoDenegado("Solo quien radicó la PQRS la reabre")
    if p.estado != E.RESPONDIDA:
        raise ValidacionError("Solo se reabre una PQRS respondida y aún no cerrada")
    await _mensaje(db, actor, p, data.texto)
    p.estado = E.EN_TRAMITE
    p.fecha_limite = d.sumar_dias_habiles(hoy_bogota(), d.PLAZO_DIAS_HABILES)
    await db.flush()
    await db.refresh(p)
    return p


async def desistir(db: AsyncSession, actor: Actor, pqrs_id: uuid.UUID, motivo: str) -> Pqrs:
    p = await obtener(db, actor, pqrs_id)
    if not _es_autor(actor, p) and actor.role not in d.PUEDE_GESTIONAR_PQRS:
        raise PermisoDenegado("Solo quien radicó la PQRS puede desistir de ella")
    if p.estado not in d.ABIERTAS:
        raise ValidacionError("Solo se desiste de una PQRS que aún no tiene respuesta")
    await _mensaje(db, actor, p, f"Desistimiento: {motivo}")
    p.estado = E.DESISTIDA
    await db.flush()
    await db.refresh(p)
    return p


# --- Integración con mantenimiento -------------------------------------------------------------


async def convertir_en_novedad(db: AsyncSession, actor: Actor, pqrs_id: uuid.UUID, data: NovedadDesdePqrsIn) -> Pqrs:
    """Una PQRS de mantenimiento se vuelve una novedad del activo afectado (módulo de mantenimiento)."""
    exigir(actor, d.PUEDE_GESTIONAR_PQRS, "convertir PQRS en novedades")
    p = await obtener(db, actor, pqrs_id)
    if p.novedad_id is not None:
        raise ValidacionError("Esta PQRS ya tiene una novedad de mantenimiento")
    n = await novedades.reportar(
        db,
        actor,
        NovedadIn(
            activo_id=data.activo_id,
            descripcion=f"{p.radicado}: {p.asunto}. {p.descripcion}"[:4000],
            prioridad=PrioridadNovedad(data.prioridad),
        ),
    )
    p.novedad_id = n.id
    if p.estado == E.RADICADA:
        p.estado = E.EN_TRAMITE
    await _mensaje(db, actor, p, f"Se creó la novedad de mantenimiento {n.codigo} para atenderla.", interno=True)
    await db.flush()
    await db.refresh(p)
    return p
