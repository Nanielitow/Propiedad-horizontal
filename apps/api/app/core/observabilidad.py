"""Alertas de errores con Sentry (API y worker). Sin SENTRY_DSN no hace nada.

Privacidad: no se envían datos personales ni secretos. Sin cookies, sin cabeceras de autorización, sin el cuerpo de
las peticiones (formularios, contraseñas), y los tokens de las URL se ocultan. Solo errores (sin trazas de rendimiento),
para no gastar la cuota gratuita.
"""

import os
import re
from typing import Any

import sentry_sdk

from app.core.config import get_settings

_SENSIBLES = {"authorization", "cookie", "set-cookie", "x-api-key", "proxy-authorization"}
_TOKEN_EN_URL = re.compile(r"((?:token|key|password|clave|firma|signature|x-amz-[a-z-]+)=)[^&#\s]+", re.IGNORECASE)


def depurar_evento(event: dict[str, Any], _hint: dict[str, Any] | None = None) -> dict[str, Any]:
    """Quita datos sensibles antes de que el evento salga del servidor."""
    req = event.get("request") or {}
    if isinstance(req.get("headers"), dict):
        req["headers"] = {k: ("[oculto]" if k.lower() in _SENSIBLES else v) for k, v in req["headers"].items()}
    req.pop("cookies", None)
    req.pop("data", None)
    for campo in ("url", "query_string"):
        if isinstance(req.get(campo), str):
            req[campo] = _TOKEN_EN_URL.sub(r"\1[oculto]", req[campo])
    event.pop("user", None)
    return event


def iniciar_sentry(componente: str) -> bool:
    dsn = get_settings().sentry_dsn
    if not dsn:
        return False
    sentry_sdk.init(
        dsn=dsn,
        environment=get_settings().environment,
        release=os.environ.get("RAILWAY_GIT_COMMIT_SHA") or None,
        server_name=componente,
        send_default_pii=False,
        max_request_body_size="never",
        include_local_variables=False,  # las variables locales pueden traer datos de residentes
        traces_sample_rate=0.0,
        before_send=depurar_evento,  # type: ignore[arg-type]
    )
    return True
