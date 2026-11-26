"""Tareas del módulo de activos y mantenimiento.

- activos.programacion (00:30): mantiene 12 meses de actividades por plan y
  reestima por horómetro los planes por horas de uso.
- activos.alertas (7:10): avisos del día agrupados en un correo por persona.
- activos.novedad_critica: correo inmediato al reportar una novedad crítica
  (la API la encola después del commit).

La lógica vive en los servicios async; cada copropiedad se procesa con una
sesión propia con contexto SYSTEM, y un fallo en una no detiene a las demás.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.rls import set_rls_context
from app.db.session import SyncSessionLocal
from app.models import Membership, Tenant, User
from app.models.enums import UserRole
from app.services.activos import alertas, planes
from app.services.comun import hoy_bogota
from app.services.notifications.email import email_enabled, maintenance_alerts, send_email
from app.workers.celery_app import celery_app

log = logging.getLogger(__name__)


def _tenants() -> list[tuple[uuid.UUID, str, str, bool]]:
    with SyncSessionLocal() as db:
        filas = db.execute(
            select(Tenant.id, Tenant.name, Tenant.slug, Tenant.is_demo).where(Tenant.deleted_at.is_(None))
        )
        return [(r[0], r[1], r[2], r[3]) for r in filas]


async def _en_tenant[T](tenant_id: uuid.UUID, trabajo: Callable[[AsyncSession], Awaitable[T]]) -> T:
    engine = create_async_engine(get_settings().database_url)
    try:
        async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as db:
            await set_rls_context(db, tenant_id=tenant_id, role="SYSTEM")
            return await trabajo(db)
    finally:
        await engine.dispose()


async def _personal(db: AsyncSession, tenant_id: uuid.UUID) -> list[tuple[uuid.UUID, str, UserRole]]:
    filas = await db.execute(
        select(User.id, User.email, Membership.role)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.tenant_id == tenant_id, User.is_active, Membership.role != UserRole.RESIDENTE)
    )
    return [(i, str(e), r) for i, e, r in filas]


def _enviar(tenant: str, slug: str, por_correo: dict[str, list[tuple[str, str]]], *, demo: bool) -> int:
    url = f"{get_settings().app_url.rstrip('/')}/{slug}/activos"
    orden = list(alertas.SECCIONES.values())
    for correo, items in por_correo.items():
        items.sort(key=lambda it: orden.index(it[0]))
        asunto, texto, html = maintenance_alerts(tenant_name=tenant, items=items, url=url)
        send_email([correo], asunto, texto, html, demo=demo)
    return len(por_correo)


@celery_app.task(name="activos.programacion")
def programacion() -> dict[str, int]:
    creadas = movidas = 0
    for tenant_id, nombre, _, _ in _tenants():

        async def trabajo(db: AsyncSession) -> tuple[int, int]:
            c = await planes.extender_programacion(db)
            m = await planes.reestimar_por_horas(db)
            await db.commit()
            return c, m

        try:
            c, m = asyncio.run(_en_tenant(tenant_id, trabajo))
            creadas, movidas = creadas + c, movidas + m
        except Exception:
            log.exception("programación de mantenimiento falló en %s", nombre)
    log.info("programación de mantenimiento: %s actividades creadas, %s reestimadas", creadas, movidas)
    return {"creadas": creadas, "reestimadas": movidas}


@celery_app.task(name="activos.alertas")
def alertas_diarias() -> dict[str, int]:
    """Calcula, registra y envía. Si el correo falla, la transacción se revierte y los
    avisos se reintentan en la próxima ejecución en lugar de perderse."""
    hoy = hoy_bogota()
    total_avisos = correos = 0
    for tenant_id, nombre, slug, es_demo in _tenants():

        async def trabajo(
            db: AsyncSession,
            tenant_id: uuid.UUID = tenant_id,
            nombre: str = nombre,
            slug: str = slug,
            es_demo: bool = es_demo,
        ) -> tuple[int, int]:
            nuevos = await alertas.registrar_nuevos(db, tenant_id, await alertas.calcular(db, hoy))
            enviados = 0
            if nuevos and email_enabled():
                por_correo = alertas.agrupar_por_destinatario(nuevos, await _personal(db, tenant_id))
                enviados = _enviar(nombre, slug, por_correo, demo=es_demo)
            await db.commit()
            return len(nuevos), enviados

        try:
            n, c = asyncio.run(_en_tenant(tenant_id, trabajo))
            total_avisos, correos = total_avisos + n, correos + c
        except Exception:
            log.exception("alertas de mantenimiento fallaron en %s", nombre)
    log.info("alertas de mantenimiento: %s avisos nuevos, %s correos", total_avisos, correos)
    return {"avisos": total_avisos, "correos": correos}


@celery_app.task(name="activos.novedad_critica", autoretry_for=(OSError,), retry_backoff=60, max_retries=5)
def novedad_critica(tenant_id: str, novedad_id: str) -> dict[str, int]:
    tid, nid = uuid.UUID(tenant_id), uuid.UUID(novedad_id)
    with SyncSessionLocal() as s:
        tenant = s.get(Tenant, tid)
    if tenant is None:
        return {"enviados": 0}

    async def trabajo(db: AsyncSession) -> int:
        fila = (
            await db.execute(
                text(
                    "SELECT n.codigo, a.codigo_interno, a.nombre, a.ubicacion, n.descripcion, n.riesgo_identificado"
                    "  FROM novedades n JOIN activos a ON a.id = n.activo_id WHERE n.id = :id AND n.prioridad = 'CRITICA'"
                ),
                {"id": nid},
            )
        ).first()
        if fila is None:
            return 0
        codigo, cod_activo, activo, ubicacion, descripcion, riesgo = fila
        mensaje = f"{codigo} en {cod_activo} {activo} ({ubicacion}): {descripcion[:200]}" + (
            f" · Riesgo: {riesgo[:120]}" if riesgo else ""
        )
        aviso = alertas.Aviso("novedad_critica", nid, mensaje, hoy_bogota())
        if not await alertas.registrar_nuevos(db, tid, [aviso]):
            return 0  # ya se avisó
        enviados = 0
        if email_enabled():
            enviados = _enviar(
                tenant.name,
                tenant.slug,
                alertas.agrupar_por_destinatario([aviso], await _personal(db, tid)),
                demo=tenant.is_demo,
            )
        await db.commit()
        return enviados

    return {"enviados": asyncio.run(_en_tenant(tid, trabajo))}
