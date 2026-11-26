"""Correos de la cuenta (invitación, recuperación de clave, nuevo acceso).

La API arma el correo y lo encola: así no espera al servidor SMTP ni falla si está lento. El enlace viaja en el
mensaje de la cola (Redis privado) y vence solo; nunca se escribe en los registros.
"""

import logging

from app.services.notifications.email import email_enabled, send_email
from app.workers.celery_app import celery_app

log = logging.getLogger(__name__)


@celery_app.task(name="cuentas.correo", autoretry_for=(OSError,), retry_backoff=30, max_retries=5)
def correo(destino: str, asunto: str, texto: str, html: str) -> dict[str, int]:
    if not email_enabled():
        log.warning("correo de cuenta sin enviar (SMTP_HOST vacío): %s", asunto)
        return {"enviados": 0}
    # No sale de una copropiedad de ejemplo: las invitaciones están bloqueadas en la demo y a las cuentas
    # demo (@*.demo) el filtro de dominios ficticios nunca les escribe.
    send_email([destino], asunto, texto, html, demo=False)
    return {"enviados": 1}
