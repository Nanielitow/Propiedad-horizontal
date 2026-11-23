"""Novedades (fallas y correctivos): reporte y flujo hasta su cierre.

REPORTADA -> EN_GESTION -> (PENDIENTE_COTIZACION) -> PROGRAMADA -> EN_EJECUCION -> CERRADA
y DESCARTADA (con motivo) para duplicados o falsas alarmas. Cerrar y descartar es
de la administración. La máquina de estados también la impone el trigger.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MantenimientoEjecutado, Membership, Novedad, QuoteComparison
from app.models.enums import EstadoActivo, EstadoNovedad, PrioridadNovedad, UserRole
from app.schemas.activos import NovedadAvance, NovedadIn
from app.services.activos import activos as servicio_activos
from app.services.activos import catalogo
from app.services.activos.dominio import (
    PUEDE_CERRAR_NOVEDAD,
    PUEDE_GESTIONAR_NOVEDAD,
    PUEDE_REPORTAR_NOVEDAD,
    TRANSICIONES_NOVEDAD,
)
from app.services.comun import (
    Actor,
    NoEncontrado,
    PermisoDenegado,
    TransicionInvalida,
    ValidacionError,
    exigir,
    fijar_motivo,
)

N = EstadoNovedad


async def reportar(db: AsyncSession, actor: Actor, data: NovedadIn) -> Novedad:
    """Cualquier rol operativo (incluido el técnico desde el QR) reporta fallas."""
    exigir(actor, PUEDE_REPORTAR_NOVEDAD, "reportar novedades")
    activo = await servicio_activos.obtener(db, actor, data.activo_id)
    servicio_activos._vigente(activo)
    if data.poner_fuera_de_servicio and data.prioridad != PrioridadNovedad.CRITICA:
        raise ValidacionError("Solo una novedad crítica pone el activo fuera de servicio al reportarla")
    await fijar_motivo(db, None)
    nov = Novedad(
        id=uuid.uuid4(),
        tenant_id=actor.tenant_id,
        activo_id=activo.id,
        reportado_por_id=actor.user_id,
        descripcion=data.descripcion,
        prioridad=data.prioridad,
        riesgo_identificado=data.riesgo_identificado,
    )
    db.add(nov)
    await db.flush()
    # El técnico no edita activos: si es él quien reporta, la administración decide el estado
    if (
        data.poner_fuera_de_servicio
        and activo.estado != EstadoActivo.FUERA_DE_SERVICIO
        and actor.role != UserRole.MANTENIMIENTO
    ):
        await fijar_motivo(db, f"Novedad crítica {nov.codigo}: {data.descripcion[:200]}")
        activo.estado = EstadoActivo.FUERA_DE_SERVICIO
        await db.flush()
        await fijar_motivo(db, None)
    return nov


async def obtener(db: AsyncSession, actor: Actor, novedad_id: uuid.UUID) -> Novedad:
    n = await db.get(Novedad, novedad_id)
    if n is None or n.tenant_id != actor.tenant_id:
        raise NoEncontrado("Novedad no encontrada")
    return n


async def avanzar(db: AsyncSession, actor: Actor, novedad_id: uuid.UUID, data: NovedadAvance) -> Novedad:
    """Pasa la novedad al siguiente estado del flujo con los datos de ese paso."""
    exigir(actor, PUEDE_GESTIONAR_NOVEDAD, "gestionar novedades")
    nov = await obtener(db, actor, novedad_id)
    destino = data.estado
    if destino not in TRANSICIONES_NOVEDAD[nov.estado]:
        if not TRANSICIONES_NOVEDAD[nov.estado]:
            raise TransicionInvalida(f"La novedad {nov.codigo} ya está {nov.estado.value.lower()}")
        raise TransicionInvalida(f"No se puede pasar de {nov.estado.value} a {destino.value}")
    if destino in (N.CERRADA, N.DESCARTADA):
        exigir(actor, PUEDE_CERRAR_NOVEDAD, "cerrar o descartar novedades")
    if actor.role == UserRole.MANTENIMIENTO and nov.asignado_a_id != actor.user_id:
        raise PermisoDenegado("Solo puede actualizar las novedades que tiene asignadas")
    if actor.role == UserRole.MANTENIMIENTO and (data.asignado_a_id or data.contratista_asignado_id):
        raise PermisoDenegado("La asignación la hace la administración")

    if destino == N.PROGRAMADA and not (
        data.contratista_asignado_id or data.asignado_a_id or nov.contratista_asignado_id or nov.asignado_a_id
    ):
        raise ValidacionError("Para programar la atención asigne un contratista o un técnico")
    if destino == N.DESCARTADA and not data.motivo_descarte:
        raise ValidacionError("Indique el motivo para descartar la novedad (mínimo 10 caracteres)")
    if destino == N.CERRADA and not (data.solucion_implementada or nov.solucion_implementada):
        resuelta = await db.scalar(
            select(MantenimientoEjecutado.id).where(
                MantenimientoEjecutado.novedad_id == nov.id, MantenimientoEjecutado.anulado_at.is_(None)
            )
        )
        if resuelta is None:
            raise ValidacionError("Para cerrar la novedad registre la solución o el mantenimiento que la resolvió")

    if data.contratista_asignado_id:
        await catalogo.contratista(db, actor, data.contratista_asignado_id)
    if data.asignado_a_id:
        rol = await db.scalar(
            select(Membership.role).where(
                Membership.tenant_id == actor.tenant_id, Membership.user_id == data.asignado_a_id
            )
        )
        if rol not in (UserRole.MANTENIMIENTO, UserRole.AUXILIAR, UserRole.ADMIN):
            raise ValidacionError("Solo se asigna a personal de mantenimiento o de la administración")
    if data.cotizacion_id:
        cot = await db.get(QuoteComparison, data.cotizacion_id)
        if cot is None or cot.tenant_id != actor.tenant_id:
            raise NoEncontrado("Comparación de cotizaciones no encontrada")

    await fijar_motivo(db, data.motivo_descarte or data.nota)
    for campo in (
        "contratista_asignado_id",
        "asignado_a_id",
        "cotizacion_id",
        "diagnostico",
        "solucion_implementada",
        "costo_reparacion",
        "motivo_descarte",
    ):
        valor = getattr(data, campo)
        if valor is not None:
            setattr(nov, campo, valor)
    nov.estado = destino
    if destino in (N.CERRADA, N.DESCARTADA):
        nov.cerrada_por_id = actor.user_id
        nov.cerrada_at = datetime.now(UTC)
    await db.flush()
    await fijar_motivo(db, None)
    await db.refresh(nov, ["fecha_atencion", "updated_at"])
    return nov
