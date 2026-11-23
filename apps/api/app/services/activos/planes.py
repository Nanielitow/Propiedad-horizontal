"""Plan preventivo y actividades programadas.

El PLAN es la regla («motobomba: mensual»); cada ACTIVIDAD es una fecha concreta.
- Calendario fijo: al aprobar se generan las fechas de los próximos 12 meses, y la
  tarea diaria extiende el horizonte para que siempre haya un año programado.
- Desde la última ejecución / por horas de uso: hay UNA actividad pendiente; la
  siguiente la crea el trigger al registrar el mantenimiento (ver 0005, §10.5).
Reprogramar nunca borra la fecha original: queda el historial con motivo.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ActividadProgramada,
    LecturaUso,
    MantenimientoEjecutado,
    Membership,
    PlanPreventivo,
    Reprogramacion,
)
from app.models.enums import BaseCalculo, EstadoActividad, Periodicidad, UserRole
from app.schemas.activos import PlanIn, PlanUpdate, ReprogramacionIn
from app.services.activos import activos as servicio_activos
from app.services.activos import catalogo
from app.services.activos.dominio import (
    PUEDE_APROBAR_PLAN,
    PUEDE_CREAR_PLAN,
    PUEDE_REPROGRAMAR,
    estado_por_horas,
    fechas_programables,
    sumar_meses,
)
from app.services.comun import (
    TZ,
    Actor,
    NoEncontrado,
    TransicionInvalida,
    ValidacionError,
    exigir,
    fijar_motivo,
    hoy_bogota,
)

HORIZONTE_MESES = 12
A = EstadoActividad


async def obtener_plan(db: AsyncSession, actor: Actor, plan_id: uuid.UUID) -> PlanPreventivo:
    p = await db.get(PlanPreventivo, plan_id)
    if p is None or p.tenant_id != actor.tenant_id:
        raise NoEncontrado("Plan no encontrado")
    return p


async def crear_plan(db: AsyncSession, actor: Actor, data: PlanIn) -> PlanPreventivo:
    """El auxiliar puede proponer planes; solo la administración los aprueba (y entonces se programan)."""
    exigir(actor, PUEDE_CREAR_PLAN, "crear planes de mantenimiento")
    activo = await servicio_activos.obtener(db, actor, data.activo_id)
    servicio_activos._vigente(activo)
    await catalogo.contratista(db, actor, data.contratista_id)
    plan = PlanPreventivo(id=uuid.uuid4(), tenant_id=actor.tenant_id, **data.model_dump())
    db.add(plan)
    await db.flush()
    return plan


async def editar_plan(db: AsyncSession, actor: Actor, plan_id: uuid.UUID, data: PlanUpdate) -> PlanPreventivo:
    """Solo datos que no cambian el calendario. Para otra periodicidad: pausar este plan y crear otro."""
    exigir(actor, PUEDE_CREAR_PLAN, "editar planes de mantenimiento")
    plan = await obtener_plan(db, actor, plan_id)
    cambios = data.model_dump(exclude_unset=True)
    if "contratista_id" in cambios:
        await catalogo.contratista(db, actor, cambios["contratista_id"])
    for campo, valor in cambios.items():
        setattr(plan, campo, valor)
    await db.flush()
    return plan


async def _pendientes(db: AsyncSession, plan_id: uuid.UUID) -> int:
    return int(
        await db.scalar(
            select(func.count()).where(
                ActividadProgramada.plan_id == plan_id, ActividadProgramada.estado == A.PROGRAMADA
            )
        )
        or 0
    )


async def generar_actividades(db: AsyncSession, plan: PlanPreventivo, hoy: date | None = None) -> int:
    """Crea las actividades que falten (idempotente: única por plan y fecha original). Devuelve cuántas creó."""
    if not plan.activo or plan.aprobado_at is None:
        return 0
    hoy = hoy or hoy_bogota()
    if plan.periodicidad == Periodicidad.POR_HORAS_USO or plan.base_calculo == BaseCalculo.DESDE_ULTIMA_EJECUCION:
        if await _pendientes(db, plan.id):
            return 0
        fechas = [max(plan.fecha_inicio, hoy)]
    else:
        fechas = fechas_programables(
            plan.fecha_inicio,
            plan.periodicidad,
            desde=max(plan.fecha_inicio, hoy),
            hasta=sumar_meses(hoy, HORIZONTE_MESES),
        )
    if not fechas:
        return 0
    resultado = await db.execute(
        insert(ActividadProgramada.__table__)
        .values(
            [
                {
                    "id": uuid.uuid4(),
                    "tenant_id": plan.tenant_id,
                    "plan_id": plan.id,
                    "activo_id": plan.activo_id,
                    "fecha_programada": f,
                    "fecha_original": f,
                }
                for f in fechas
            ]
        )
        .on_conflict_do_nothing(index_elements=["plan_id", "fecha_original"])
    )
    return int(resultado.rowcount or 0)  # type: ignore[attr-defined]


async def aprobar_plan(
    db: AsyncSession, actor: Actor, plan_id: uuid.UUID, *, hoy: date | None = None
) -> tuple[PlanPreventivo, int]:
    exigir(actor, PUEDE_APROBAR_PLAN, "aprobar planes de mantenimiento")
    plan = await obtener_plan(db, actor, plan_id)
    if plan.aprobado_at is not None:
        raise TransicionInvalida("El plan ya está aprobado")
    if not plan.activo:
        raise ValidacionError("El plan está pausado")
    plan.aprobado_por_id = actor.user_id
    plan.aprobado_at = datetime.now(UTC)
    await db.flush()
    return plan, await generar_actividades(db, plan, hoy)


async def pausar_plan(db: AsyncSession, actor: Actor, plan_id: uuid.UUID, motivo: str) -> int:
    """Pausa el plan y cancela sus actividades futuras (no se borran). Devuelve cuántas canceló."""
    exigir(actor, PUEDE_APROBAR_PLAN, "pausar planes de mantenimiento")
    plan = await obtener_plan(db, actor, plan_id)
    if not plan.activo:
        raise TransicionInvalida("El plan ya está pausado")
    await fijar_motivo(db, motivo)
    plan.activo = False
    resultado = await db.execute(
        update(ActividadProgramada)
        .where(ActividadProgramada.plan_id == plan.id, ActividadProgramada.estado == A.PROGRAMADA)
        .values(estado=A.CANCELADA)
    )
    await db.flush()
    await fijar_motivo(db, None)
    return int(resultado.rowcount or 0)  # type: ignore[attr-defined]


async def reanudar_plan(db: AsyncSession, actor: Actor, plan_id: uuid.UUID, *, hoy: date | None = None) -> int:
    exigir(actor, PUEDE_APROBAR_PLAN, "reanudar planes de mantenimiento")
    plan = await obtener_plan(db, actor, plan_id)
    if plan.activo:
        raise TransicionInvalida("El plan ya está activo")
    plan.activo = True
    await db.flush()
    return await generar_actividades(db, plan, hoy)


async def obtener_actividad(db: AsyncSession, actor: Actor, actividad_id: uuid.UUID) -> ActividadProgramada:
    a = await db.get(ActividadProgramada, actividad_id)
    if a is None or a.tenant_id != actor.tenant_id:
        raise NoEncontrado("Actividad no encontrada")
    return a


async def reprogramar(
    db: AsyncSession, actor: Actor, actividad_id: uuid.UUID, data: ReprogramacionIn
) -> ActividadProgramada:
    """Cambia la fecha dejando la anterior, la nueva y el motivo (el trigger exige este registro)."""
    exigir(actor, PUEDE_REPROGRAMAR, "reprogramar actividades")
    act = await obtener_actividad(db, actor, actividad_id)
    if act.estado != A.PROGRAMADA:
        raise TransicionInvalida(f"La actividad ya está {act.estado.value.lower()}: no se reprograma")
    if data.nueva_fecha == act.fecha_programada:
        raise ValidacionError("La nueva fecha es igual a la actual")
    if data.nueva_fecha < hoy_bogota():
        raise ValidacionError("No se reprograma a una fecha pasada")
    db.add(
        Reprogramacion(
            id=uuid.uuid4(),
            tenant_id=actor.tenant_id,
            actividad_id=act.id,
            fecha_anterior=act.fecha_programada,
            nueva_fecha=data.nueva_fecha,
            motivo=data.motivo,
            usuario_id=actor.user_id,
        )
    )
    await db.flush()  # la reprogramación debe existir ANTES del cambio de fecha
    await fijar_motivo(db, data.motivo)
    act.fecha_programada = data.nueva_fecha
    await db.flush()
    await fijar_motivo(db, None)
    return act


async def asignar(
    db: AsyncSession, actor: Actor, actividad_id: uuid.UUID, usuario_id: uuid.UUID | None
) -> ActividadProgramada:
    """Asigna la actividad a un técnico interno (rol Mantenimiento) o la deja sin asignar."""
    exigir(actor, PUEDE_REPROGRAMAR, "asignar actividades")
    act = await obtener_actividad(db, actor, actividad_id)
    if act.estado != A.PROGRAMADA:
        raise TransicionInvalida("Solo se asignan actividades pendientes")
    if usuario_id is not None:
        rol = await db.scalar(
            select(Membership.role).where(Membership.tenant_id == actor.tenant_id, Membership.user_id == usuario_id)
        )
        if rol not in (UserRole.MANTENIMIENTO, UserRole.AUXILIAR, UserRole.ADMIN):
            raise ValidacionError("Solo se asigna a personal de mantenimiento o de la administración")
    act.asignado_a_id = usuario_id
    await db.flush()
    return act


async def extender_programacion(db: AsyncSession, hoy: date | None = None) -> int:
    """Tarea diaria (como SYSTEM): mantiene 12 meses programados en cada plan aprobado y activo."""
    planes = await db.scalars(
        select(PlanPreventivo).where(PlanPreventivo.activo, PlanPreventivo.aprobado_at.is_not(None))
    )
    total = 0
    for plan in planes:
        total += await generar_actividades(db, plan, hoy)
    return total


async def reestimar_por_horas(db: AsyncSession, hoy: date | None = None, *, tolerancia_dias: int = 3) -> int:
    """Tarea nocturna (SYSTEM): ajusta la fecha de las actividades de planes por horas de uso
    según el horómetro. Cada ajuste queda como reprogramación con su motivo. Devuelve cuántas movió."""
    hoy = hoy or hoy_bogota()
    planes_horas = await db.scalars(
        select(PlanPreventivo).where(
            PlanPreventivo.periodicidad == Periodicidad.POR_HORAS_USO,
            PlanPreventivo.activo,
            PlanPreventivo.aprobado_at.is_not(None),
        )
    )
    movidas = 0
    for plan in planes_horas:
        act = await db.scalar(
            select(ActividadProgramada).where(
                ActividadProgramada.plan_id == plan.id, ActividadProgramada.estado == A.PROGRAMADA
            )
        )
        lecturas = list(
            await db.execute(
                select(LecturaUso.fecha, LecturaUso.horas_acumuladas)
                .where(LecturaUso.activo_id == plan.activo_id)
                .order_by(LecturaUso.fecha)
            )
        )
        if act is None or not lecturas or plan.intervalo_horas is None:
            continue
        ultima_fecha, ultima = lecturas[-1]
        ejecucion = await db.scalar(
            select(func.max(MantenimientoEjecutado.fecha_ejecucion))
            .join(ActividadProgramada, ActividadProgramada.id == MantenimientoEjecutado.actividad_id)
            .where(ActividadProgramada.plan_id == plan.id, MantenimientoEjecutado.anulado_at.is_(None))
        )
        # Horas de referencia: la lectura vigente al último mantenimiento; sin mantenimientos, la primera
        previas = [h for f, h in lecturas if ejecucion is not None and f.astimezone(TZ).date() <= ejecucion]
        base = previas[-1] if previas else lecturas[0][1]
        # Uso diario: lecturas de los últimos 30 días
        ventana = [(f, h) for f, h in lecturas if (ultima_fecha - f).days <= 30]
        dias = (ventana[-1][0] - ventana[0][0]).total_seconds() / 86400
        uso = (ventana[-1][1] - ventana[0][1]) / Decimal(str(dias)) if dias >= 1 else None
        estado = estado_por_horas(plan.intervalo_horas, ultima - base, uso, hoy)
        nueva = estado.fecha_estimada
        if nueva is None or nueva < hoy or abs((nueva - act.fecha_programada).days) < tolerancia_dias:
            continue
        db.add(
            Reprogramacion(
                id=uuid.uuid4(),
                tenant_id=plan.tenant_id,
                actividad_id=act.id,
                fecha_anterior=act.fecha_programada,
                nueva_fecha=nueva,
                motivo=f"Reestimada por horómetro: quedan {estado.horas_restantes} h de {plan.intervalo_horas} h",
            )
        )
        await db.flush()
        act.fecha_programada = nueva
        await db.flush()
        movidas += 1
    return movidas
