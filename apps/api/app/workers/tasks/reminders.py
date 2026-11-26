"""Recordatorios de vencimientos (Celery beat, todos los días a las 7:00 Bogotá).

Para cada vencimiento ACTIVO (confirmado) cuya distancia en días coincide con
uno de sus reminder_days (30, 15, 7, 1 por defecto) o que vence hoy:
  - canal "in_app": queda registrado (el panel lo muestra);
  - canal "email": se envía a los administradores del edificio (si hay SMTP).

Idempotencia: restricción única (deadline_id, notify_on, channel) + INSERT ...
ON CONFLICT DO NOTHING RETURNING. Solo se envía si la fila se insertó de verdad,
y el insert del correo va en un SAVEPOINT: si el envío falla, se deshace y el
correo se reintentará en la siguiente ejecución en lugar de perderse.
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SyncSessionLocal
from app.models import Deadline, DeadlineNotification, Document, Membership, Tenant, User
from app.models.enums import DeadlineStatus, UserRole
from app.services.extraction.deadlines import TZ
from app.services.ingestion.pipeline import _system_session
from app.services.notifications.email import deadline_reminder, email_enabled, send_email
from app.workers.celery_app import celery_app

log = logging.getLogger(__name__)
_TABLE = DeadlineNotification.__table__


def _register(db: Session, tenant_id: uuid.UUID, deadline_id: uuid.UUID, today: object, channel: str) -> bool:
    """True si la notificación es nueva (no existía para hoy y este canal)."""
    return (
        db.execute(
            insert(_TABLE)
            .values(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                deadline_id=deadline_id,
                notify_on=today,
                channel=channel,
                sent_at=datetime.now(UTC),
            )
            .on_conflict_do_nothing(index_elements=["deadline_id", "notify_on", "channel"])
            .returning(_TABLE.c.id)
        ).first()
        is not None
    )


@celery_app.task(name="deadlines.send_reminders")
def send_deadline_reminders() -> dict[str, int]:
    today = datetime.now(TZ).date()
    settings = get_settings()
    with SyncSessionLocal() as db:  # tenants y users son globales (sin RLS)
        tenants = list(
            db.execute(select(Tenant.id, Tenant.name, Tenant.slug, Tenant.is_demo).where(Tenant.deleted_at.is_(None)))
        )

    in_app = emails = failures = 0
    for tenant_id, tenant_name, tenant_slug, tenant_demo in tenants:
        with _system_session(tenant_id) as db:  # contexto RLS por edificio
            due = [
                (d, doc_title)
                for d, doc_title in db.execute(
                    select(Deadline, Document.title)
                    .join(Document, Document.id == Deadline.document_id)
                    .where(Deadline.status == DeadlineStatus.ACTIVE, Deadline.due_date >= today)
                )
                if (d.due_date - today).days == 0 or (d.due_date - today).days in (d.reminder_days or [])
            ]
            if not due:
                continue
            admins = (
                list(
                    db.scalars(
                        select(User.email)
                        .join(Membership, Membership.user_id == User.id)
                        .where(Membership.tenant_id == tenant_id, Membership.role == UserRole.ADMIN, User.is_active)
                    )
                )
                if email_enabled()
                else []
            )

            for d, doc_title in due:
                days_left = (d.due_date - today).days
                if _register(db, tenant_id, d.id, today, "in_app"):
                    in_app += 1
                    log.info("recordatorio: '%s' vence en %s días (%s)", d.title, days_left, d.due_date)
                if not admins:
                    continue
                try:
                    with db.begin_nested():  # SAVEPOINT: si el envío falla, no queda registrado
                        if _register(db, tenant_id, d.id, today, "email"):
                            subject, text, html = deadline_reminder(
                                tenant_name=tenant_name,
                                title=d.title,
                                due=d.due_date.strftime("%d/%m/%Y"),
                                days_left=days_left,
                                provider=d.provider_name,
                                document=doc_title,
                                url=f"{settings.app_url}/{tenant_slug}/deadlines",
                            )
                            send_email(admins, subject, text, html, demo=tenant_demo)
                            emails += 1
                except Exception:
                    failures += 1
                    log.exception("no se pudo enviar el correo del vencimiento %s; se reintentará", d.id)
            db.commit()
    return {"tenants": len(tenants), "in_app": in_app, "emails": emails, "email_failures": failures}
