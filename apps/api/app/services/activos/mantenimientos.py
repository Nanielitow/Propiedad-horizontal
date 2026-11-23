"""Historial de intervenciones: registro inmutable de mantenimientos.

Al registrar, la base de datos (trigger privilegiado) marca la actividad como
ejecutada, actualiza el estado del activo y, si el plan cuenta desde la última
ejecución, programa la siguiente fecha. Cada recomendación accionable del técnico
se crea como tarea rastreable en la misma transacción.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ActividadProgramada, Document, MantenimientoEjecutado, Novedad, RecomendacionTecnica
from app.models.enums import EstadoActividad, TipoMantenimiento, UserRole
from app.schemas.activos import MantenimientoIn
from app.services.activos import activos as servicio_activos
from app.services.activos import catalogo
from app.services.activos.dominio import NOVEDAD_ABIERTA, PUEDE_ANULAR_MANTENIMIENTO, PUEDE_REGISTRAR_MANTENIMIENTO
from app.services.comun import (
    Actor,
    NoEncontrado,
    PermisoDenegado,
    TransicionInvalida,
    ValidacionError,
    exigir,
    fijar_motivo,
    hoy_bogota,
)


async def _documento(db: AsyncSession, actor: Actor, document_id: uuid.UUID | None) -> None:
    if document_id and not await db.scalar(
        select(Document.id).where(
            Document.id == document_id, Document.tenant_id == actor.tenant_id, Document.deleted_at.is_(None)
        )
    ):
        raise NoEncontrado("Documento no encontrado")


async def registrar(
    db: AsyncSession, actor: Actor, data: MantenimientoIn
) -> tuple[MantenimientoEjecutado, list[RecomendacionTecnica]]:
    exigir(actor, PUEDE_REGISTRAR_MANTENIMIENTO, "registrar mantenimientos")
    activo = await servicio_activos.obtener(db, actor, data.activo_id)
    servicio_activos._vigente(activo)
    if data.fecha_ejecucion > hoy_bogota():
        raise ValidacionError("La fecha de ejecución no puede estar en el futuro")
    if data.fecha_proximo_recomendado and data.fecha_proximo_recomendado <= data.fecha_ejecucion:
        raise ValidacionError("La próxima fecha recomendada debe ser posterior a la ejecución")
    await catalogo.contratista(db, actor, data.contratista_id)
    await _documento(db, actor, data.informe_documento_id)
    await _documento(db, actor, data.factura_documento_id)

    if data.actividad_id:
        act = await db.get(ActividadProgramada, data.actividad_id)
        if act is None or act.tenant_id != actor.tenant_id:
            raise NoEncontrado("Actividad programada no encontrada")
        if act.activo_id != activo.id:
            raise ValidacionError("La actividad programada pertenece a otro activo")
        if act.estado != EstadoActividad.PROGRAMADA:
            raise TransicionInvalida(f"La actividad ya está {act.estado.value.lower()}")
        if data.tipo != TipoMantenimiento.PREVENTIVO:
            raise ValidacionError("Una actividad del plan preventivo se cumple con un mantenimiento preventivo")
        # El técnico registra lo que tiene asignado (o lo que nadie tiene asignado)
        if actor.role == UserRole.MANTENIMIENTO and act.asignado_a_id not in (None, actor.user_id):
            raise PermisoDenegado("Esta actividad está asignada a otra persona")
    if data.novedad_id:
        nov = await db.get(Novedad, data.novedad_id)
        if nov is None or nov.tenant_id != actor.tenant_id:
            raise NoEncontrado("Novedad no encontrada")
        if nov.activo_id != activo.id:
            raise ValidacionError("La novedad pertenece a otro activo")
        if nov.estado not in NOVEDAD_ABIERTA:
            raise TransicionInvalida(f"La novedad {nov.codigo} ya está {nov.estado.value.lower()}")
    for r in data.recomendaciones:
        if r.fecha_limite and r.fecha_limite < data.fecha_ejecucion:
            raise ValidacionError("La fecha límite de una recomendación no puede ser anterior a la ejecución")

    await fijar_motivo(db, None)
    m = MantenimientoEjecutado(
        id=uuid.uuid4(),
        tenant_id=actor.tenant_id,
        registrado_por_id=actor.user_id,
        **data.model_dump(exclude={"recomendaciones", "checklist"}),
        checklist=[i.model_dump() for i in data.checklist],
    )
    db.add(m)
    await db.flush()

    recomendaciones = [
        RecomendacionTecnica(
            id=uuid.uuid4(),
            tenant_id=actor.tenant_id,
            activo_id=activo.id,
            mantenimiento_origen_id=m.id,
            creado_por_id=actor.user_id,
            **r.model_dump(),
        )
        for r in data.recomendaciones
    ]
    db.add_all(recomendaciones)
    await db.flush()
    # Los efectos del trigger (estado del activo, actividad cumplida) ya están en la base
    await db.refresh(activo)
    return m, recomendaciones


async def obtener(db: AsyncSession, actor: Actor, mantenimiento_id: uuid.UUID) -> MantenimientoEjecutado:
    m = await db.get(MantenimientoEjecutado, mantenimiento_id)
    if m is None or m.tenant_id != actor.tenant_id:
        raise NoEncontrado("Mantenimiento no encontrado")
    return m


async def anular(db: AsyncSession, actor: Actor, mantenimiento_id: uuid.UUID, motivo: str) -> MantenimientoEjecutado:
    """El historial no se edita: un registro errado se anula (queda visible) y se crea de nuevo.
    Si cumplía una actividad, la actividad vuelve a quedar pendiente."""
    exigir(actor, PUEDE_ANULAR_MANTENIMIENTO, "anular mantenimientos")
    motivo = motivo.strip()
    if len(motivo) < 10:
        raise ValidacionError("El motivo de la anulación debe tener al menos 10 caracteres")
    m = await obtener(db, actor, mantenimiento_id)
    if m.anulado_at is not None:
        raise TransicionInvalida(f"El mantenimiento {m.codigo} ya está anulado")
    await fijar_motivo(db, motivo)
    m.anulado_por_id = actor.user_id
    m.anulado_at = datetime.now(UTC)
    m.motivo_anulacion = motivo
    await db.flush()
    await fijar_motivo(db, None)
    return m
