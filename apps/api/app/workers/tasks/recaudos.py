"""Tareas del módulo de recaudos.

- recaudos.notificar_alertas: correo a los administradores. La API la encola
  DESPUÉS del commit (si la transacción se revirtiera, no habría nada que avisar).
  Idempotente: solo envía alertas con notificada_at vacío y lo marca al enviar.
- recaudos.transferencias_sin_verificar: diaria; alerta por transferencias que
  llevan más de N días sin verificarse (N en tenants.settings, 3 por defecto).

Las tareas usan sesiones síncronas con contexto SYSTEM; la lógica vive en el
servicio async, así que se ejecuta con una sesión async de corta vida.
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.rls import set_rls_context
from app.db.session import SyncSessionLocal
from app.models import AlertaRecaudo, Membership, Tenant, User
from app.models.enums import UserRole
from app.services.ingestion.pipeline import _system_session
from app.services.notifications.email import email_enabled, recaudo_alerts, send_email
from app.services.recaudos.alertas import DIAS_VERIFICACION_POR_DEFECTO, detectar_transferencias_sin_verificar
from app.workers.celery_app import celery_app

log = logging.getLogger(__name__)


def encolar_notificacion(tenant_id: uuid.UUID, alerta_ids: list[uuid.UUID]) -> None:
    """Para la API: llamar después del commit."""
    if alerta_ids:
        notificar_alertas.delay(str(tenant_id), [str(a) for a in alerta_ids])


@celery_app.task(name="recaudos.notificar_alertas", autoretry_for=(OSError,), retry_backoff=60, max_retries=5)
def notificar_alertas(tenant_id: str, alerta_ids: list[str]) -> dict[str, int]:
    if not email_enabled():
        return {"enviadas": 0}
    tid = uuid.UUID(tenant_id)
    with SyncSessionLocal() as db:
        tenant = db.get(Tenant, tid)
    if tenant is None:
        return {"enviadas": 0}
    with _system_session(tid) as db:
        alertas = list(
            db.scalars(
                select(AlertaRecaudo)
                .where(AlertaRecaudo.id.in_([uuid.UUID(a) for a in alerta_ids]), AlertaRecaudo.notificada_at.is_(None))
                .order_by(AlertaRecaudo.created_at)
                .with_for_update(skip_locked=True)  # dos reintentos simultáneos no envían doble
            )
        )
        if not alertas:
            return {"enviadas": 0}
        destinatarios = list(
            db.scalars(
                select(User.email)
                .join(Membership, Membership.user_id == User.id)
                .where(Membership.tenant_id == tid, Membership.role == UserRole.ADMIN, User.is_active)
            )
        )
        if not destinatarios:
            return {"enviadas": 0}
        url = f"{get_settings().app_url}/{tenant.slug}/recaudos/alertas"
        subject, text, html = recaudo_alerts(
            tenant_name=tenant.name, alertas=[(a.severidad.value, a.mensaje) for a in alertas], url=url
        )
        send_email(destinatarios, subject, text, html, demo=tenant.is_demo)  # si falla, no se marca y se reintenta
        ahora = datetime.now(UTC)
        for a in alertas:
            a.notificada_at = ahora
        db.commit()
    return {"enviadas": len(alertas)}


async def _detectar(tenant_id: uuid.UUID, dias: int) -> list[uuid.UUID]:
    engine = create_async_engine(get_settings().database_url)
    try:
        async with async_sessionmaker(engine, class_=AsyncSession)() as db:
            await set_rls_context(db, tenant_id=tenant_id, role="SYSTEM")
            alertas = await detectar_transferencias_sin_verificar(db, tenant_id, dias=dias)
            await db.commit()
            return [a.id for a in alertas]
    finally:
        await engine.dispose()


@celery_app.task(name="recaudos.transferencias_sin_verificar")
def transferencias_sin_verificar() -> dict[str, int]:
    with SyncSessionLocal() as db:
        tenants = list(db.execute(select(Tenant.id, Tenant.settings).where(Tenant.deleted_at.is_(None))))
    total = 0
    for tenant_id, settings in tenants:
        dias = int((settings or {}).get("recaudos_dias_verificacion", DIAS_VERIFICACION_POR_DEFECTO))
        nuevas = asyncio.run(_detectar(tenant_id, dias))
        if nuevas:
            total += len(nuevas)
            notificar_alertas.delay(str(tenant_id), [str(a) for a in nuevas])
    log.info("transferencias sin verificar: %s alertas nuevas", total)
    return {"alertas": total}


# --- Corte mensual (día 1, 6:00) -----------------------------------------------------


async def _generar_corte(tenant_id: uuid.UUID, anio: int, mes: int) -> tuple[bytes, list[tuple[str, str]], str] | None:
    """Genera y guarda el corte (como SYSTEM). None si ya existía o no hubo recaudos ese mes."""
    from app.models import CorteMensual, Recaudo
    from app.services.recaudos.cortes import generar_corte, nombre_periodo
    from app.services.recaudos.reportes import _fin_de_mes, _inicio

    engine = create_async_engine(get_settings().database_url)
    try:
        async with async_sessionmaker(engine, class_=AsyncSession)() as db:
            await set_rls_context(db, tenant_id=tenant_id, role="SYSTEM")
            desde = datetime(anio, mes, 1).date()
            if await db.scalar(select(CorteMensual.id).where(CorteMensual.periodo == desde)):
                return None
            hubo = await db.scalar(
                select(Recaudo.id)
                .where(
                    Recaudo.fecha_recaudo >= _inicio(desde),
                    Recaudo.fecha_recaudo < _inicio(_fin_de_mes(desde)) + timedelta(days=1),
                )
                .limit(1)
            )
            if hubo is None:  # la copropiedad no usó el módulo ese mes
                return None
            generado = await generar_corte(db, tenant_id, anio, mes)
            await db.commit()
            return generado.pdf, generado.reporte.resumen, nombre_periodo(desde)
    finally:
        await engine.dispose()


@celery_app.task(name="recaudos.corte_mensual")
def corte_mensual(anio: int | None = None, mes: int | None = None) -> dict[str, int]:
    from app.services.notifications.email import monthly_cut
    from app.services.recaudos.cortes import mes_anterior

    if anio is None or mes is None:
        anio, mes = mes_anterior()
    with SyncSessionLocal() as db:
        tenants = list(
            db.execute(select(Tenant.id, Tenant.name, Tenant.slug, Tenant.is_demo).where(Tenant.deleted_at.is_(None)))
        )
    generados = enviados = 0
    for tenant_id, nombre, slug, es_demo in tenants:
        resultado = asyncio.run(_generar_corte(tenant_id, anio, mes))
        if resultado is None:
            continue
        generados += 1
        pdf, lineas, periodo = resultado
        if not email_enabled():
            continue
        with _system_session(tenant_id) as db:
            destinatarios = list(
                db.scalars(
                    select(User.email)
                    .join(Membership, Membership.user_id == User.id)
                    .where(
                        Membership.tenant_id == tenant_id,
                        Membership.role.in_([UserRole.ADMIN, UserRole.CONSEJO]),
                        User.is_active,
                    )
                )
            )
        if destinatarios:
            asunto, texto, html = monthly_cut(
                tenant_name=nombre,
                period=periodo,
                lines=lineas,
                url=f"{get_settings().app_url}/{slug}/recaudos/reportes",
            )
            try:
                send_email(
                    destinatarios,
                    asunto,
                    texto,
                    html,
                    [(f"corte-recaudos-{anio}-{mes:02d}.pdf", pdf, "application/pdf")],
                    demo=es_demo,
                )
                enviados += 1
            except OSError:  # el corte ya quedó guardado; el correo no debe tumbar a las demás copropiedades
                log.exception("no se pudo enviar el corte de %s", nombre)
    log.info("cortes mensuales %s-%02d: %s generados, %s enviados", anio, mes, generados, enviados)
    return {"generados": generados, "enviados": enviados}
