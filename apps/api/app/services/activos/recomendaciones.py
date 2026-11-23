"""Recomendaciones técnicas: cada sugerencia del técnico convertida en tarea rastreable."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MantenimientoEjecutado, Membership, RecomendacionTecnica
from app.models.enums import EstadoRecomendacion, UserRole
from app.schemas.activos import RecomendacionIn, RecomendacionUpdate
from app.services.activos import activos as servicio_activos
from app.services.activos.dominio import PUEDE_DESCARTAR_RECOMENDACION, PUEDE_GESTIONAR_RECOMENDACION
from app.services.comun import (
    Actor,
    NoEncontrado,
    PermisoDenegado,
    TransicionInvalida,
    ValidacionError,
    exigir,
    fijar_motivo,
)

E = EstadoRecomendacion
CERRADAS = frozenset({E.EJECUTADA, E.DESCARTADA_CON_JUSTIFICACION})


async def _responsable(db: AsyncSession, actor: Actor, usuario_id: uuid.UUID | None) -> None:
    if usuario_id is None:
        return
    rol = await db.scalar(
        select(Membership.role).where(Membership.tenant_id == actor.tenant_id, Membership.user_id == usuario_id)
    )
    if rol is None or rol in (UserRole.RESIDENTE, UserRole.CONSEJO):
        raise ValidacionError("El responsable debe ser parte del personal de la copropiedad")


async def crear(db: AsyncSession, actor: Actor, data: RecomendacionIn) -> RecomendacionTecnica:
    """Recomendación que no viene de un mantenimiento (inspección o decisión de la administración)."""
    exigir(actor, PUEDE_GESTIONAR_RECOMENDACION, "registrar recomendaciones")
    activo = await servicio_activos.obtener(db, actor, data.activo_id)
    servicio_activos._vigente(activo)
    await _responsable(db, actor, data.responsable_id)
    r = RecomendacionTecnica(
        id=uuid.uuid4(), tenant_id=actor.tenant_id, creado_por_id=actor.user_id, **data.model_dump()
    )
    db.add(r)
    await db.flush()
    return r


async def obtener(db: AsyncSession, actor: Actor, recomendacion_id: uuid.UUID) -> RecomendacionTecnica:
    r = await db.get(RecomendacionTecnica, recomendacion_id)
    if r is None or r.tenant_id != actor.tenant_id:
        raise NoEncontrado("Recomendación no encontrada")
    return r


async def actualizar(
    db: AsyncSession, actor: Actor, recomendacion_id: uuid.UUID, data: RecomendacionUpdate
) -> RecomendacionTecnica:
    exigir(actor, PUEDE_GESTIONAR_RECOMENDACION, "actualizar recomendaciones")
    r = await obtener(db, actor, recomendacion_id)
    if r.estado in CERRADAS:
        raise TransicionInvalida("La recomendación ya está cerrada")
    cambios = data.model_dump(exclude_unset=True)
    if actor.role == UserRole.MANTENIMIENTO:
        if r.responsable_id != actor.user_id:
            raise PermisoDenegado("Solo puede actualizar las recomendaciones que tiene a cargo")
        if set(cambios) - {"estado", "mantenimiento_ejecucion_id"}:
            raise PermisoDenegado("El técnico solo actualiza el avance de la recomendación")
    if cambios.get("estado") == E.DESCARTADA_CON_JUSTIFICACION:
        exigir(actor, PUEDE_DESCARTAR_RECOMENDACION, "descartar recomendaciones")
        if not (cambios.get("justificacion_descarte") or r.justificacion_descarte):
            raise ValidacionError("Para descartar una recomendación escriba la justificación (mínimo 10 caracteres)")
    if "responsable_id" in cambios:
        await _responsable(db, actor, cambios["responsable_id"])
    if cambios.get("mantenimiento_ejecucion_id"):
        m = await db.get(MantenimientoEjecutado, cambios["mantenimiento_ejecucion_id"])
        if m is None or m.tenant_id != actor.tenant_id or m.activo_id != r.activo_id or m.anulado_at is not None:
            raise ValidacionError("El mantenimiento indicado no corresponde a este activo")
    await fijar_motivo(db, cambios.get("justificacion_descarte") or cambios.get("observaciones_administracion"))
    for campo, valor in cambios.items():
        setattr(r, campo, valor)
    await db.flush()
    await fijar_motivo(db, None)
    return r
