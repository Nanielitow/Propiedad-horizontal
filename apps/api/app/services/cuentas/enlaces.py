"""Enlaces de un solo uso: invitación (definir la clave por primera vez) y recuperación de clave.

El token viaja solo en el enlace del correo; en la base queda su SHA-256. Emitir un enlace nuevo anula los
anteriores del mismo tipo, y usarlo lo consume.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_link_token, new_link_token
from app.models import AccountToken, Tenant, User
from app.services.notifications.email import correo_cuenta

INVITACION = "INVITACION"
RECUPERACION = "RECUPERACION"
VIGENCIA = {INVITACION: timedelta(days=7), RECUPERACION: timedelta(hours=1)}
RUTA = {INVITACION: "activar", RECUPERACION: "restablecer"}

# Versión de la política de tratamiento de datos que acepta quien activa su cuenta (Ley 1581 de 2012)
POLITICA_VERSION = "2026-11-25"

ENLACE_INVALIDO = HTTPException(
    status.HTTP_400_BAD_REQUEST, "El enlace no es válido o ya expiró. Pida uno nuevo a la administración."
)


@dataclass(frozen=True)
class Correo:
    """Correo listo para encolar (la API no espera al servidor SMTP)."""

    destino: str
    asunto: str
    texto: str
    html: str
    enlace: str | None = None  # enlace de activación (para que el dueño pueda copiarlo y enviarlo él mismo)


def es_cuenta_demo(email: str) -> bool:
    """Cuentas compartidas de la demo pública: nadie puede cambiarles la clave."""
    return email.strip().lower().endswith(".demo")


async def emitir(
    db: AsyncSession,
    user: User,
    tipo: str,
    *,
    tenant_id: uuid.UUID | None = None,
    creado_por: uuid.UUID | None = None,
) -> str:
    """Anula los enlaces vigentes del mismo tipo y crea uno nuevo. Devuelve la URL completa."""
    ahora = datetime.now(UTC)
    await db.execute(
        update(AccountToken)
        .where(AccountToken.user_id == user.id, AccountToken.kind == tipo, AccountToken.used_at.is_(None))
        .values(used_at=ahora)
    )
    token, digest = new_link_token()
    db.add(
        AccountToken(
            user_id=user.id,
            kind=tipo,
            token_hash=digest,
            tenant_id=tenant_id,
            created_by_id=creado_por,
            expires_at=ahora + VIGENCIA[tipo],
        )
    )
    await db.flush()
    return f"{get_settings().app_url}/{RUTA[tipo]}?token={token}"


async def validar(db: AsyncSession, token: str, tipo: str | None = None) -> tuple[AccountToken, User]:
    """Enlace vigente y sin usar, de un usuario activo. Si no, 400 con un mensaje genérico."""
    if not token or len(token) > 200:
        raise ENLACE_INVALIDO
    fila = (
        await db.execute(
            select(AccountToken, User)
            .join(User, User.id == AccountToken.user_id)
            .where(AccountToken.token_hash == hash_link_token(token))
        )
    ).first()
    if fila is None:
        raise ENLACE_INVALIDO
    enlace, user = fila
    if (
        enlace.used_at is not None
        or enlace.expires_at <= datetime.now(UTC)
        or (tipo is not None and enlace.kind != tipo)
        or not user.is_active
    ):
        raise ENLACE_INVALIDO
    return enlace, user


async def nombre_copropiedad(db: AsyncSession, tenant_id: uuid.UUID | None) -> str | None:
    if tenant_id is None:
        return None
    return await db.scalar(select(Tenant.name).where(Tenant.id == tenant_id))


def correo_invitacion(user: User, url: str, copropiedad: str | None, invita: str | None) -> Correo:
    donde = f" de {copropiedad}" if copropiedad else ""
    quien = f"{invita} lo invitó" if invita else "Lo invitaron"
    asunto, texto, html = correo_cuenta(
        titulo=f"Active su cuenta{donde}",
        parrafos=[
            f"Hola, {user.full_name.split()[0]}:",
            f"{quien} a PH Gestión, la plataforma de administración{donde}.",
            "Para entrar, defina su contraseña con el botón de abajo. El enlace vence en 7 días y solo sirve una vez.",
        ],
        url=url,
        boton="Definir mi contraseña",
        pie="Si no esperaba este correo, ignórelo: sin definir la contraseña nadie puede entrar con su cuenta.",
    )
    return Correo(user.email, asunto, texto, html, enlace=url)


def correo_recuperacion(user: User, url: str) -> Correo:
    asunto, texto, html = correo_cuenta(
        titulo="Restablecer su contraseña",
        parrafos=[
            f"Hola, {user.full_name.split()[0]}:",
            "Recibimos una solicitud para restablecer la contraseña de su cuenta en PH Gestión.",
            "El enlace vence en 1 hora y solo sirve una vez. Al usarlo se cierran las sesiones abiertas.",
        ],
        url=url,
        boton="Elegir una contraseña nueva",
        pie="Si no lo pidió usted, ignore este correo: su contraseña actual sigue funcionando.",
    )
    return Correo(user.email, asunto, texto, html)


def correo_nuevo_acceso(user: User, copropiedad: str, rol: str) -> Correo:
    asunto, texto, html = correo_cuenta(
        titulo=f"Nuevo acceso: {copropiedad}",
        parrafos=[
            f"Hola, {user.full_name.split()[0]}:",
            f"Ahora tiene acceso a {copropiedad} en PH Gestión con el rol {rol}.",
            "Entre con su correo y su contraseña de siempre; la nueva copropiedad aparece en el selector del menú.",
        ],
        url=f"{get_settings().app_url}/login",
        boton="Entrar a PH Gestión",
        pie="Si cree que es un error, comuníquese con la administración de la copropiedad.",
    )
    return Correo(user.email, asunto, texto, html)
