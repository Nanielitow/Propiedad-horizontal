"""Avisos por correo del portal del residente (la API los encola después del commit).

- portal.pqrs_radicada: a la administración y recepción.
- portal.pqrs_respondida: a quien radicó.
- portal.circular_publicada: a los destinatarios (con cuenta o solo con correo en el directorio).
- portal.reserva_solicitada: a la administración (si la zona exige aprobación).
- portal.reserva_decidida: al residente que reservó.

Cada tarea abre su sesión con contexto SYSTEM. Sin SMTP configurado no envía nada.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.rls import set_rls_context
from app.models import Circular, Membership, Pqrs, Reserva, Tenant, User, ZonaSocial
from app.models.enums import EstadoReserva, UserRole
from app.services.notifications.email import aviso_portal, email_enabled, send_email
from app.services.portal import circulares
from app.workers.celery_app import celery_app

log = logging.getLogger(__name__)
_REINTENTOS = {"autoretry_for": (OSError,), "retry_backoff": 60, "max_retries": 5}


async def _en_tenant[T](tenant_id: uuid.UUID, trabajo: Callable[[AsyncSession, Tenant], Awaitable[T]]) -> T | None:
    engine = create_async_engine(get_settings().database_url)
    try:
        async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as db:
            await set_rls_context(db, tenant_id=tenant_id, role="SYSTEM")
            tenant = await db.get(Tenant, tenant_id)
            if tenant is None:
                return None
            return await trabajo(db, tenant)
    finally:
        await engine.dispose()


def _url(tenant: Tenant, ruta: str) -> str:
    return f"{get_settings().app_url.rstrip('/')}/{tenant.slug}/{ruta}"


async def _personal(db: AsyncSession, tenant_id: uuid.UUID, roles: tuple[UserRole, ...]) -> list[str]:
    filas = await db.scalars(
        select(User.email)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.tenant_id == tenant_id, Membership.role.in_(roles), User.is_active)
    )
    return [str(e) for e in filas]


def _correr(tenant_id: str, trabajo: Callable[[AsyncSession, Tenant], Awaitable[int]]) -> dict[str, int]:
    if not email_enabled():
        return {"enviados": 0}
    return {"enviados": asyncio.run(_en_tenant(uuid.UUID(tenant_id), trabajo)) or 0}


@celery_app.task(name="portal.pqrs_radicada", **_REINTENTOS)
def pqrs_radicada(tenant_id: str, pqrs_id: str) -> dict[str, int]:
    async def trabajo(db: AsyncSession, tenant: Tenant) -> int:
        p = await db.get(Pqrs, uuid.UUID(pqrs_id))
        if p is None:
            return 0
        destinos = await _personal(db, tenant.id, (UserRole.ADMIN, UserRole.AUXILIAR))
        if not destinos:
            return 0
        asunto, texto, html = aviso_portal(
            tenant_name=tenant.name,
            seccion="PQRS",
            titulo=f"Nueva {p.tipo.value.lower()}: {p.radicado}",
            parrafos=[
                f"{p.solicitante_nombre} radicó «{p.asunto}».",
                f"Plazo de respuesta: {p.fecha_limite:%d/%m/%Y}.",
            ],
            cita=p.descripcion[:600],
            url=_url(tenant, f"portal/pqrs/{p.id}"),
            boton="Atender la PQRS",
        )
        send_email(destinos, asunto, texto, html)
        return len(destinos)

    return _correr(tenant_id, trabajo)


@celery_app.task(name="portal.pqrs_respondida", **_REINTENTOS)
def pqrs_respondida(tenant_id: str, pqrs_id: str, respuesta: str) -> dict[str, int]:
    async def trabajo(db: AsyncSession, tenant: Tenant) -> int:
        p = await db.get(Pqrs, uuid.UUID(pqrs_id))
        if p is None:
            return 0
        u = await db.get(User, p.radicado_por_id)
        # Si la radicó recepción a nombre de alguien, el contacto es el que se dejó en la PQRS
        destino = p.solicitante_contacto if p.canal.value != "PORTAL" else (u.email if u else None)
        if not destino or "@" not in destino:
            return 0
        asunto, texto, html = aviso_portal(
            tenant_name=tenant.name,
            seccion="PQRS",
            titulo=f"Respuesta a su PQRS {p.radicado}",
            parrafos=[f"La administración respondió «{p.asunto}»."],
            cita=respuesta[:1500],
            url=_url(tenant, f"mi-portal/pqrs/{p.id}"),
            boton="Ver y calificar la respuesta",
        )
        send_email([destino], asunto, texto, html)
        return 1

    return _correr(tenant_id, trabajo)


@celery_app.task(name="portal.circular_publicada", **_REINTENTOS)
def circular_publicada(tenant_id: str, circular_id: str) -> dict[str, int]:
    async def trabajo(db: AsyncSession, tenant: Tenant) -> int:
        c = await db.get(Circular, uuid.UUID(circular_id))
        if c is None or not c.enviar_correo or c.correos_enviados:
            return 0  # ya se envió (reintento) o no se pidió correo
        destinos = await circulares.destinatarios(db, c)
        resumen = c.cuerpo.replace("#", "").replace("*", "")[:900]
        enviados = 0
        for x in destinos:
            asunto, texto, html = aviso_portal(
                tenant_name=tenant.name,
                seccion="Circular" + (" importante" if c.importante else ""),
                titulo=c.titulo,
                parrafos=[f"Estimado(a) {x.nombre.split()[0]}:"],
                cita=resumen + ("…" if len(c.cuerpo) > 900 else ""),
                url=_url(tenant, "mi-portal/circulares"),
                boton="Leer la circular completa",
            )
            try:
                send_email([x.email], asunto, texto, html)
                enviados += 1
            except OSError:
                log.warning("no se pudo enviar la circular %s a %s", c.id, x.email)
        c.correos_enviados = enviados
        await db.commit()
        return enviados

    return _correr(tenant_id, trabajo)


@celery_app.task(name="portal.reserva_solicitada", **_REINTENTOS)
def reserva_solicitada(tenant_id: str, reserva_id: str) -> dict[str, int]:
    async def trabajo(db: AsyncSession, tenant: Tenant) -> int:
        r = await db.get(Reserva, uuid.UUID(reserva_id))
        if r is None or r.estado != EstadoReserva.SOLICITADA:
            return 0
        z = await db.get(ZonaSocial, r.zona_id)
        destinos = await _personal(db, tenant.id, (UserRole.ADMIN, UserRole.AUXILIAR))
        if not destinos:
            return 0
        horario = f"de {r.hora_inicio:%H:%M} a {r.hora_fin:%H:%M}" if r.hora_inicio and r.hora_fin else "todo el día"
        asunto, texto, html = aviso_portal(
            tenant_name=tenant.name,
            seccion="Reservas",
            titulo=f"Solicitud de reserva: {z.nombre if z else 'zona social'}",
            parrafos=[
                f"{r.solicitante} solicitó el {r.fecha_evento:%d/%m/%Y} {horario}.",
                "Apruébela o recházela desde la plataforma.",
            ],
            url=_url(tenant, "portal/reservas"),
            boton="Revisar la solicitud",
        )
        send_email(destinos, asunto, texto, html)
        return len(destinos)

    return _correr(tenant_id, trabajo)


@celery_app.task(name="portal.reserva_decidida", **_REINTENTOS)
def reserva_decidida(tenant_id: str, reserva_id: str) -> dict[str, int]:
    async def trabajo(db: AsyncSession, tenant: Tenant) -> int:
        r = await db.get(Reserva, uuid.UUID(reserva_id))
        if r is None or r.creado_por_id is None:
            return 0
        u = await db.get(User, r.creado_por_id)
        z = await db.get(ZonaSocial, r.zona_id)
        if u is None:
            return 0
        aprobada = r.estado == EstadoReserva.CONFIRMADA
        parrafos = [
            f"{z.nombre if z else 'La zona'} el {r.fecha_evento:%d/%m/%Y}: su reserva fue {'aprobada' if aprobada else 'rechazada'}."
        ]
        if aprobada and z and (z.tarifa_alquiler or z.tarifa_aseo):
            parrafos.append("Recuerde cancelar el valor del alquiler en la administración antes del evento.")
        asunto, texto, html = aviso_portal(
            tenant_name=tenant.name,
            seccion="Reservas",
            titulo=f"Reserva {'aprobada' if aprobada else 'rechazada'}",
            parrafos=parrafos,
            cita=r.motivo_decision,
            url=_url(tenant, "mi-portal/reservas"),
            boton="Ver mis reservas",
        )
        send_email([str(u.email)], asunto, texto, html)
        return 1

    return _correr(tenant_id, trabajo)
