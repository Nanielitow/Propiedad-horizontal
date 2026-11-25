"""Circulares de la administración: borrador, publicación (numerada), lectura con acuse y archivo.

Una circular publicada no se edita (se publica una aclaración). Puede dirigirse a toda la
copropiedad o a torres específicas; el residente ve las de las torres de sus unidades.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Circular, CircularLectura, Document, Membership, Persona, UnidadPersona, Unit, User
from app.models.enums import EstadoCircular, UserRole
from app.schemas.portal import CircularIn, CircularUpdate
from app.services.comun import Actor, NoEncontrado, ValidacionError, exigir
from app.services.portal import dominio as d
from app.services.unidades.dominio import normalizar_torre

R = UserRole
EC = EstadoCircular


async def obtener(db: AsyncSession, actor: Actor, circular_id: uuid.UUID) -> Circular:
    c = await db.get(Circular, circular_id)  # la RLS oculta los borradores al residente
    if c is None or c.tenant_id != actor.tenant_id:
        raise NoEncontrado("Circular no encontrada")
    return c


async def _validar(
    db: AsyncSession, actor: Actor, torres: list[str] | None, document_id: uuid.UUID | None
) -> list[str] | None:
    if document_id is not None:
        doc = await db.scalar(select(Document.id).where(Document.id == document_id, Document.deleted_at.is_(None)))
        if doc is None:
            raise NoEncontrado("El documento adjunto no existe")
    if torres is None:
        return None
    normal = sorted({normalizar_torre(t) for t in torres if normalizar_torre(t)})
    if normal:
        existentes = set(await db.scalars(select(Unit.tower).where(Unit.activa.is_(True)).distinct()))
        faltan = [t for t in normal if t not in existentes]
        if faltan:
            raise ValidacionError(f"No hay unidades en la torre {', '.join(faltan)}")
    return normal


async def crear(db: AsyncSession, actor: Actor, data: CircularIn) -> Circular:
    exigir(actor, d.PUEDE_REDACTAR_CIRCULAR, "redactar circulares")
    torres = await _validar(db, actor, data.torres, data.document_id)
    c = Circular(
        id=uuid.uuid4(),
        tenant_id=actor.tenant_id,
        creada_por_id=actor.user_id,
        **{**data.model_dump(), "torres": torres or []},
    )
    db.add(c)
    await db.flush()
    return c


async def editar(db: AsyncSession, actor: Actor, circular_id: uuid.UUID, data: CircularUpdate) -> Circular:
    exigir(actor, d.PUEDE_REDACTAR_CIRCULAR, "editar circulares")
    c = await obtener(db, actor, circular_id)
    if c.estado != EC.BORRADOR:
        raise ValidacionError("Una circular publicada no se edita: publique una aclaración")
    cambios = data.model_dump(exclude_unset=True)
    if "torres" in cambios or "document_id" in cambios:
        torres = await _validar(db, actor, cambios.get("torres"), cambios.get("document_id"))
        if torres is not None:
            cambios["torres"] = torres
    for k, v in cambios.items():
        setattr(c, k, v if not (k == "torres" and v is None) else [])
    await db.flush()
    return c


async def publicar(db: AsyncSession, actor: Actor, circular_id: uuid.UUID) -> Circular:
    exigir(actor, d.PUEDE_PUBLICAR_CIRCULAR, "publicar circulares")
    c = await obtener(db, actor, circular_id)
    if c.estado != EC.BORRADOR:
        raise ValidacionError("La circular ya fue publicada")
    c.estado = EC.PUBLICADA
    c.publicada_por_id = actor.user_id
    await db.flush()
    await db.refresh(c)  # consecutivo y fecha los pone el trigger
    return c


async def archivar(db: AsyncSession, actor: Actor, circular_id: uuid.UUID) -> Circular:
    exigir(actor, d.PUEDE_PUBLICAR_CIRCULAR, "archivar circulares")
    c = await obtener(db, actor, circular_id)
    if c.estado != EC.PUBLICADA:
        raise ValidacionError("Solo se archivan circulares publicadas")
    c.estado = EC.ARCHIVADA
    await db.flush()
    return c


# --- Destinatarios y lectura -------------------------------------------------------------------


async def torres_del_usuario(db: AsyncSession, actor: Actor) -> set[str] | None:
    """Torres de las unidades del residente; None para el personal (ve todas)."""
    if actor.role != R.RESIDENTE:
        return None
    filas = await db.scalars(
        select(Unit.tower)
        .join(UnidadPersona, UnidadPersona.unidad_id == Unit.id)
        .join(Persona, Persona.id == UnidadPersona.persona_id)
        .where(Persona.user_id == actor.user_id, UnidadPersona.fecha_fin.is_(None))
    )
    return set(filas)


def le_aplica(c: Circular, torres: set[str] | None) -> bool:
    return torres is None or not c.torres or bool(set(c.torres) & torres)


async def marcar_leida(db: AsyncSession, actor: Actor, circular_id: uuid.UUID) -> None:
    c = await obtener(db, actor, circular_id)
    if c.estado == EC.BORRADOR:
        raise ValidacionError("La circular aún no está publicada")
    await db.execute(
        insert(CircularLectura)
        .values(circular_id=c.id, user_id=actor.user_id, tenant_id=actor.tenant_id)
        .on_conflict_do_nothing(index_elements=["circular_id", "user_id"])
    )


@dataclass(frozen=True)
class Destinatario:
    nombre: str
    email: str
    user_id: uuid.UUID | None


async def destinatarios(db: AsyncSession, c: Circular) -> list[Destinatario]:
    """Correos de quienes deben recibirla: residentes con cuenta y personas del directorio con
    correo (propietarios sin cuenta incluidos), de las torres indicadas. Sin duplicados."""
    q = (
        select(Persona.nombre_completo, Persona.email, Persona.user_id)
        .join(UnidadPersona, UnidadPersona.persona_id == Persona.id)
        .join(Unit, Unit.id == UnidadPersona.unidad_id)
        .where(UnidadPersona.fecha_fin.is_(None), Persona.activa.is_(True), Persona.email.is_not(None))
    )
    if c.torres:
        q = q.where(Unit.tower.in_(c.torres))
    vistos: dict[str, Destinatario] = {}
    for nombre, email, uid in (await db.execute(q)).all():
        vistos.setdefault(str(email).lower(), Destinatario(nombre, str(email), uid))
    # Residentes con cuenta que no estén en el directorio (p. ej. demo o recién invitados)
    if not c.torres:
        filas = await db.execute(
            select(User.full_name, User.email, User.id)
            .join(Membership, Membership.user_id == User.id)
            .where(Membership.tenant_id == c.tenant_id, Membership.role == R.RESIDENTE, User.is_active)
        )
        for nombre, email, uid in filas.all():
            vistos.setdefault(str(email).lower(), Destinatario(nombre.split(" (")[0], str(email), uid))
    return list(vistos.values())


async def estadisticas_lectura(db: AsyncSession, actor: Actor, c: Circular) -> tuple[int, int]:
    """(leídas, residentes con cuenta a quienes aplica)."""
    exigir(actor, d.PUEDE_VER_LECTURAS, "ver quién leyó la circular")
    leidas = (
        await db.scalar(select(func.count()).select_from(CircularLectura).where(CircularLectura.circular_id == c.id))
        or 0
    )
    con_cuenta = {x.user_id for x in await destinatarios(db, c) if x.user_id}
    return leidas, len(con_cuenta)
