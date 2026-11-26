"""Límite de solicitudes con Redis (ventana fija).

Objetivos:
  - COSTO: cada pregunta, comparación o resumen llama a un modelo de IA de pago;
    sin límites, un usuario (o un script con su sesión) podría disparar la factura.
  - SEGURIDAD: frenar la fuerza bruta contra el login.

Ventana fija: contador `rl:{nombre}:{sujeto}:{ventana}` con INCR + EXPIRE. Es
simple y suficiente aquí; el "pico" en el borde de dos ventanas (hasta 2x el
límite durante un instante) es aceptable para estos casos.

Si Redis no responde, se deja pasar la petición (fail-open): el límite protege
el costo, no debe tumbar el servicio.
"""

import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol

from fastapi import HTTPException, Request, status

log = logging.getLogger(__name__)


class AsyncCounter(Protocol):
    async def incr(self, name: str) -> int: ...
    async def expire(self, name: str, time: int) -> Any: ...


@dataclass(frozen=True)
class Limit:
    name: str
    limit: int
    window_seconds: int
    message: str


# -- Políticas (un solo lugar para ajustarlas) ---------------------------------
ASK_PER_MINUTE = Limit("ask-min", 20, 60, "Está haciendo preguntas muy rápido.")
ASK_PER_DAY = Limit("ask-day", 300, 86_400, "Alcanzó el límite diario de preguntas.")
SEARCH_PER_MINUTE = Limit("search-min", 60, 60, "Demasiadas búsquedas seguidas.")
UPLOADS_PER_HOUR = Limit("upload-hour", 60, 3_600, "Alcanzó el límite de subidas por hora.")
# Tareas de IA costosas: por edificio (no por usuario) para acotar el gasto total
AI_JOBS_PER_DAY = Limit("ai-jobs-day", 40, 86_400, "La copropiedad alcanzó el límite diario de análisis con IA.")
# Demo pública: todos comparten las mismas cuentas, así que un límite por usuario
# lo agotaría un solo visitante para todos. Se limita además por red (IP).
DEMO_ASK_PER_IP_DAY = Limit("demo-ask-ip", 40, 86_400, "La demo pública permite 40 preguntas al día por visitante.")
DEMO_UPLOADS_PER_IP_DAY = Limit(
    "demo-upload-ip", 10, 86_400, "La demo pública permite 10 subidas al día por visitante."
)
LOGIN_PER_ACCOUNT = Limit("login-acct", 10, 900, "Demasiados intentos de inicio de sesión.")
LOGIN_PER_IP = Limit("login-ip", 50, 900, "Demasiados intentos de inicio de sesión desde esta red.")


async def hit(redis: AsyncCounter, limit: Limit, subject: str, now: float | None = None) -> int | None:
    """Registra un uso. Devuelve None si está permitido, o los segundos que faltan
    para que se reinicie la ventana si se superó el límite."""
    now = time.time() if now is None else now
    window = int(now // limit.window_seconds)
    key = f"rl:{limit.name}:{subject}:{window}"
    try:
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, limit.window_seconds)
    except Exception:  # noqa: BLE001  (fail-open: ver docstring del módulo)
        log.warning("rate limit no disponible (Redis); se permite la petición")
        return None
    if count <= limit.limit:
        return None
    return max(1, int(limit.window_seconds - now % limit.window_seconds))


def _humanize(seconds: int) -> str:
    if seconds < 90:
        return f"{seconds} segundos"
    if seconds < 5400:
        return f"{round(seconds / 60)} minutos"
    return f"{round(seconds / 3600)} horas"


async def enforce(request: Request, limit: Limit, subject: str) -> None:
    retry_after = await hit(request.app.state.redis, limit, subject)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"{limit.message} Intente de nuevo en {_humanize(retry_after)}.",
            headers={"Retry-After": str(retry_after)},
        )


async def enforce_demo(request: Request, limit: Limit, *, demo: bool) -> None:
    """Límite adicional por visitante en los conjuntos de ejemplo (todos comparten las cuentas demo)
    o en toda la app si corre como demo pública (DEMO_MODE)."""
    from app.core.config import get_settings

    if demo or get_settings().demo_mode:
        await enforce(request, limit, client_ip(request))


def client_ip(request: Request) -> str:
    # Detrás del BFF de Next.js / un proxy, la IP real llega en X-Forwarded-For
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# Módulo de recaudos: escrituras por usuario (frena scripts o dobles clics en ráfaga)
RECAUDOS_WRITES_PER_MINUTE = Limit("recaudos-escritura", 60, 60, "Demasiadas operaciones seguidas.")
DEMO_RECAUDOS_PER_IP_DAY = Limit(
    "demo-recaudos-ip", 150, 86_400, "La demo pública permite 150 operaciones de recaudos al día por visitante."
)

# Módulo de activos y mantenimiento
ACTIVOS_WRITES_PER_MINUTE = Limit("activos-escritura", 60, 60, "Demasiadas operaciones seguidas.")
DEMO_ACTIVOS_PER_IP_DAY = Limit(
    "demo-activos-ip", 150, 86_400, "La demo pública permite 150 operaciones de mantenimiento al día por visitante."
)

# Módulo de unidades, copropietarios y residentes
UNIDADES_WRITES_PER_MINUTE = Limit("unidades-escritura", 120, 60, "Demasiadas operaciones seguidas.")
DEMO_UNIDADES_PER_IP_DAY = Limit(
    "demo-unidades-ip", 150, 86_400, "La demo pública permite 150 cambios en el censo al día por visitante."
)

# Módulo de cartera de cuotas
CARTERA_WRITES_PER_MINUTE = Limit("cartera-escritura", 120, 60, "Demasiadas operaciones seguidas.")
DEMO_CARTERA_PER_IP_DAY = Limit(
    "demo-cartera-ip", 150, 86_400, "La demo pública permite 150 operaciones de cartera al día por visitante."
)

# Portal del residente (PQRS, reservas, circulares)
PORTAL_WRITES_PER_MINUTE = Limit("portal-escritura", 30, 60, "Demasiadas operaciones seguidas.")
DEMO_PORTAL_PER_IP_DAY = Limit(
    "demo-portal-ip", 80, 86_400, "La demo pública permite 80 operaciones del portal al día por visitante."
)

# Cuentas: recuperación de clave y enlaces (frena el envío masivo de correos y la enumeración de cuentas)
RECOVER_PER_IP = Limit("recover-ip", 10, 3_600, "Demasiadas solicitudes de recuperación.")
RECOVER_PER_ACCOUNT = Limit("recover-account", 3, 3_600, "Ya enviamos varios enlaces a ese correo.")
LINKS_PER_IP = Limit("links-ip", 60, 3_600, "Demasiados intentos con enlaces.")
PASSWORD_CHANGE_PER_USER = Limit("password-user", 10, 3_600, "Demasiados intentos de cambio de contraseña.")
INVITES_PER_USER = Limit("invites-user", 100, 3_600, "Alcanzó el límite de invitaciones por hora.")
BACKUPS_PER_USER = Limit("backups-user", 6, 3_600, "Ya pidió varios respaldos en la última hora.")
