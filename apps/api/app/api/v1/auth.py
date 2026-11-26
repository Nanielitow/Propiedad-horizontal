import uuid
from datetime import UTC, datetime

import jwt
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession
from app.core.rate_limit import (
    LINKS_PER_IP,
    LOGIN_PER_ACCOUNT,
    LOGIN_PER_IP,
    PASSWORD_CHANGE_PER_USER,
    RECOVER_PER_ACCOUNT,
    RECOVER_PER_IP,
    client_ip,
    enforce,
)
from app.core.security import (
    burn_verification_time,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    sessions_cutoff,
    token_revoked,
    verify_password,
)
from app.db.rls import set_rls_context
from app.models import AccountToken, Membership, Tenant, User
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    MembershipOut,
    MeResponse,
    RefreshRequest,
    TokenPair,
    UserOut,
)
from app.schemas.cuentas import ActivarIn, CambiarClaveIn, EnlaceIn, EnlaceOut, RecuperarIn, RestablecerIn
from app.services.cuentas import enlaces
from app.workers.celery_app import celery_app

router = APIRouter(prefix="/auth", tags=["auth"])

CORREO_TASK = "cuentas.correo"

_INVALID = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")
_SESSION_EXPIRED = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="La sesión expiró")


REFRESH_REUSE_GRACE_SECONDS = 30


def _refresh_key(jti: str) -> str:
    return f"refresh:{jti}"


def _grace_key(jti: str) -> str:
    return f"refresh_grace:{jti}"


async def _issue_tokens(redis: Redis, user_id: uuid.UUID) -> TokenPair:
    access, access_ttl = create_access_token(user_id)
    refresh, jti, refresh_ttl = create_refresh_token(user_id)
    # Lista de permitidos: solo los refresh tokens registrados aquí son válidos.
    # Cerrar sesión o rotar = borrar la clave.
    await redis.set(_refresh_key(jti), str(user_id), ex=refresh_ttl)
    return TokenPair(access_token=access, expires_in=access_ttl, refresh_token=refresh, refresh_expires_in=refresh_ttl)


async def _memberships(db: AsyncSession, user_id: uuid.UUID) -> list[MembershipOut]:
    # Visible gracias a la política own_memberships (user_id = app.user_id)
    rows = await db.execute(
        select(Membership.tenant_id, Membership.role, Tenant.name, Tenant.slug, Tenant.is_demo)
        .join(Tenant, Tenant.id == Membership.tenant_id)
        .where(Membership.user_id == user_id, Tenant.deleted_at.is_(None))
        .order_by(Tenant.name)
    )
    return [
        MembershipOut(tenant_id=r.tenant_id, role=r.role, tenant_name=r.name, tenant_slug=r.slug, is_demo=r.is_demo)
        for r in rows
    ]


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, db: DbSession, request: Request) -> LoginResponse:
    email = body.email.strip().lower()
    # Fuerza bruta: límite por cuenta y por IP (antes de tocar la base o argon2)
    await enforce(request, LOGIN_PER_IP, client_ip(request))
    await enforce(request, LOGIN_PER_ACCOUNT, email)

    user = await db.scalar(select(User).where(User.email == email))
    # argon2 es CPU-intensivo a propósito: se ejecuta fuera del event loop
    if user is None or user.password_hash is None:  # inexistente o invitado sin clave: mismo tiempo
        await run_in_threadpool(burn_verification_time, body.password)
        raise _INVALID
    if not await run_in_threadpool(verify_password, body.password, user.password_hash):
        raise _INVALID
    if not user.is_active:
        raise _INVALID

    await set_rls_context(db, user_id=user.id)
    memberships = await _memberships(db, user.id)
    user.last_login_at = datetime.now(UTC)
    await db.commit()

    tokens = await _issue_tokens(request.app.state.redis, user.id)
    return LoginResponse(
        **tokens.model_dump(),
        user=_user_out(user),
        memberships=memberships,
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshRequest, db: DbSession, request: Request) -> TokenPair:
    """Rotación: el refresh token usado se invalida y se emite un par nuevo.

    GETDEL es atómico: solo una petición puede rotar un token. Pero el navegador
    suele lanzar varias peticiones a la vez cuando el acceso vence; sin más, la
    segunda recibiría 401 y cerraría la sesión del usuario. Por eso hay una
    ventana de gracia: durante unos segundos, reutilizar el token recién rotado
    devuelve EL MISMO par nuevo (no uno adicional). Pasada la ventana, reutilizar
    un token rotado es sospechoso y se rechaza."""
    try:
        user_id, jti = decode_refresh_token(body.refresh_token)
    except jwt.InvalidTokenError as exc:
        raise _SESSION_EXPIRED from exc
    redis: Redis = request.app.state.redis
    stored = await redis.getdel(_refresh_key(jti))
    if stored is None:
        cached = await redis.get(_grace_key(jti))
        if cached:
            return TokenPair.model_validate_json(cached)
        raise _SESSION_EXPIRED  # ya usado (fuera de la ventana), revocado o expirado
    if (stored.decode() if isinstance(stored, bytes) else stored) != str(user_id):
        raise _SESSION_EXPIRED
    user = await db.get(User, user_id)
    if user is None or not user.is_active or token_revoked(body.refresh_token, user.sessions_valid_after):
        raise _SESSION_EXPIRED
    tokens = await _issue_tokens(redis, user_id)
    await redis.set(_grace_key(jti), tokens.model_dump_json(), ex=REFRESH_REUSE_GRACE_SECONDS)
    return tokens


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshRequest, request: Request) -> None:
    """Revoca el refresh token (el access token expira solo en minutos)."""
    try:
        _, jti = decode_refresh_token(body.refresh_token)
    except jwt.InvalidTokenError:
        return  # token inválido: no hay nada que revocar
    await request.app.state.redis.delete(_refresh_key(jti), _grace_key(jti))


@router.get("/me", response_model=MeResponse)
async def me(user: CurrentUser, db: DbSession) -> MeResponse:
    return MeResponse(
        user=_user_out(user),
        memberships=await _memberships(db, user.id),
    )


def _user_out(user: User) -> UserOut:
    return UserOut(id=user.id, email=user.email, full_name=user.full_name, is_platform_admin=user.is_platform_admin)


# ---------------------------------------------------------------------------------------------
# Enlaces de un solo uso: activar la cuenta (invitación) y recuperar la contraseña
# ---------------------------------------------------------------------------------------------
def _encolar(correo: enlaces.Correo) -> None:
    celery_app.send_task(CORREO_TASK, args=[correo.destino, correo.asunto, correo.texto, correo.html])


async def _entrar(db: AsyncSession, request: Request, user: User) -> LoginResponse:
    """Tras definir la clave, la persona queda dentro sin volver a escribirla."""
    await set_rls_context(db, user_id=user.id)
    memberships = await _memberships(db, user.id)
    user.last_login_at = datetime.now(UTC)
    await db.commit()
    tokens = await _issue_tokens(request.app.state.redis, user.id)
    return LoginResponse(**tokens.model_dump(), user=_user_out(user), memberships=memberships)


@router.post("/enlace", response_model=EnlaceOut)
async def ver_enlace(body: EnlaceIn, db: DbSession, request: Request) -> EnlaceOut:
    """Datos para mostrar en la página del enlace (a quién pertenece, de qué copropiedad).

    POST con el token en el cuerpo, no en la ruta: las rutas quedan en los registros de acceso del servidor."""
    await enforce(request, LINKS_PER_IP, client_ip(request))
    enlace, user = await enlaces.validar(db, body.token)
    return EnlaceOut(
        tipo=enlace.kind,  # type: ignore[arg-type]
        email=user.email,
        nombre=user.full_name,
        copropiedad=await enlaces.nombre_copropiedad(db, enlace.tenant_id),
        requiere_politica=user.terms_version != enlaces.POLITICA_VERSION,
        politica_version=enlaces.POLITICA_VERSION,
    )


@router.post("/activar", response_model=LoginResponse)
async def activar(body: ActivarIn, db: DbSession, request: Request) -> LoginResponse:
    """Primera contraseña de un invitado. Exige aceptar la política de tratamiento de datos (Ley 1581)."""
    await enforce(request, LINKS_PER_IP, client_ip(request))
    enlace, user = await enlaces.validar(db, body.token, enlaces.INVITACION)
    if not body.acepta_politica:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Debe aceptar la política de tratamiento de datos")
    ahora = datetime.now(UTC)
    user.password_hash = await run_in_threadpool(hash_password, body.password)
    user.terms_accepted_at, user.terms_version = ahora, enlaces.POLITICA_VERSION
    user.sessions_valid_after = sessions_cutoff()
    enlace.used_at = ahora
    return await _entrar(db, request, user)


@router.post("/recuperar", status_code=status.HTTP_202_ACCEPTED)
async def recuperar(body: RecuperarIn, db: DbSession, request: Request) -> dict[str, str]:
    """Siempre responde lo mismo, exista o no la cuenta (no revela qué correos están registrados)."""
    email = body.email.strip().lower()
    await enforce(request, RECOVER_PER_IP, client_ip(request))
    await enforce(request, RECOVER_PER_ACCOUNT, email)
    respuesta = {"detail": "Si el correo está registrado, le llegará un enlace en unos minutos."}
    user = await db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active or enlaces.es_cuenta_demo(email):
        return respuesta
    if user.password_hash is None:  # nunca activó su cuenta: se le reenvía la invitación
        enlace_previo = await db.scalar(
            select(AccountToken.tenant_id)
            .where(AccountToken.user_id == user.id, AccountToken.kind == enlaces.INVITACION)
            .order_by(AccountToken.created_at.desc())
            .limit(1)
        )
        url = await enlaces.emitir(db, user, enlaces.INVITACION, tenant_id=enlace_previo)
        correo = enlaces.correo_invitacion(user, url, await enlaces.nombre_copropiedad(db, enlace_previo), None)
    else:
        url = await enlaces.emitir(db, user, enlaces.RECUPERACION)
        correo = enlaces.correo_recuperacion(user, url)
    await db.commit()
    _encolar(correo)
    return respuesta


@router.post("/restablecer", response_model=LoginResponse)
async def restablecer(body: RestablecerIn, db: DbSession, request: Request) -> LoginResponse:
    """Contraseña nueva con el enlace de recuperación. Cierra todas las demás sesiones."""
    await enforce(request, LINKS_PER_IP, client_ip(request))
    enlace, user = await enlaces.validar(db, body.token, enlaces.RECUPERACION)
    user.password_hash = await run_in_threadpool(hash_password, body.password)
    user.sessions_valid_after = sessions_cutoff()
    enlace.used_at = datetime.now(UTC)
    return await _entrar(db, request, user)


@router.post("/cambiar-clave", response_model=TokenPair)
async def cambiar_clave(body: CambiarClaveIn, user: CurrentUser, db: DbSession, request: Request) -> TokenPair:
    """Cambia la contraseña conociendo la actual. Cierra las demás sesiones y entrega tokens nuevos."""
    await enforce(request, PASSWORD_CHANGE_PER_USER, str(user.id))
    if enlaces.es_cuenta_demo(user.email):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Las cuentas de demostración no pueden cambiar su contraseña")
    if not await run_in_threadpool(verify_password, body.actual, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La contraseña actual no es correcta")
    if body.actual == body.nueva:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La contraseña nueva debe ser distinta de la actual")
    user.password_hash = await run_in_threadpool(hash_password, body.nueva)
    user.sessions_valid_after = sessions_cutoff()
    await db.commit()
    return await _issue_tokens(request.app.state.redis, user.id)
