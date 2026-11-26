"""Respaldo diario de la base de datos (03:00, hora de Bogotá). Solo en producción, salvo que se pida a mano.

Si falla, reintenta dos veces (cada 10 minutos) y, si sigue fallando, avisa por correo a los dueños de la plataforma.
"""

import logging

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SyncSessionLocal
from app.models import User
from app.services.notifications.email import correo_cuenta, email_enabled, send_email
from app.services.respaldos import RespaldoError, crear_respaldo
from app.workers.celery_app import celery_app

log = logging.getLogger(__name__)


def _avisar_falla(motivo: str) -> None:
    if not email_enabled():
        return
    with SyncSessionLocal() as db:  # users no tiene RLS
        destinos = list(db.scalars(select(User.email).where(User.is_platform_admin, User.is_active)))
    if not destinos:
        return
    asunto, texto, html = correo_cuenta(
        titulo="Falló el respaldo de la base de datos",
        parrafos=[
            "El respaldo automático de esta noche no se pudo completar después de 3 intentos.",
            f"Motivo: {motivo}",
            "La aplicación sigue funcionando y Neon conserva su historial de 7 días, pero conviene revisarlo hoy: "
            "en el panel de la plataforma puede intentar «Respaldar ahora».",
        ],
        url=f"{get_settings().app_url}/plataforma",
        boton="Abrir el panel de la plataforma",
        pie="Aviso automático de PH Gestión para los dueños de la plataforma.",
    )
    send_email(destinos, asunto, texto, html, demo=False)


@celery_app.task(name="respaldos.diario", bind=True, max_retries=2, default_retry_delay=600)
def diario(self, forzar: bool = False) -> dict[str, object]:  # type: ignore[no-untyped-def]
    if get_settings().environment != "production" and not forzar:
        return {"omitido": "solo se respalda automáticamente en producción"}
    try:
        return crear_respaldo()
    except Exception as exc:
        motivo = str(exc) if isinstance(exc, RespaldoError) else f"error inesperado ({type(exc).__name__})"
        log.error("respaldo falló (intento %s): %s", self.request.retries + 1, motivo)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc) from exc
        _avisar_falla(motivo)
        raise
