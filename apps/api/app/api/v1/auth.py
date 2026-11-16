import uuid
from datetime import UTC, datetime

import jwt
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession
from app.core.rate_limit import LOGIN_PER_ACCOUNT, LOGIN_PER_IP, client_ip, enforce
from app.core.security import (
    burn_verification_time,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    verify_password,
)
from app.db.rls import set_rls_context
from app.models import Membership, Tenant, User
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    MembershipOut,
    MeResponse,
    RefreshRequest,
    TokenPair,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])

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
        select(Membership.tenant_id, Membership.role, Tenant.name, Tenant.slug)
        .join(Tenant, Tenant.id == Membership.tenant_id)
        .where(Membership.user_id == user_id, Tenant.deleted_at.is_(None))
        .order_by(Tenant.name)
    )
    return [MembershipOut(tenant_id=r.tenant_id, role=r.role, tenant_name=r.name, tenant_slug=r.slug) for r in rows]


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, db: DbSession, request: Request) -> LoginResponse:
    email = body.email.strip().lower()
    # Fuerza bruta: límite por cuenta y por IP (antes de tocar la base o argon2)
    await enforce(request, LOGIN_PER_IP, client_ip(request))
    await enforce(request, LOGIN_PER_ACCOUNT, email)

    user = await db.scalar(select(User).where(User.email == email))
    # argon2 es CPU-intensivo a propósito: se ejecuta fuera del event loop
    if user is None:
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
        user=UserOut(id=user.id, email=user.email, full_name=user.full_name),
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
    if user is None or not user.is_active:
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
        user=UserOut(id=user.id, email=user.email, full_name=user.full_name),
        memberships=await _memberships(db, user.id),
    )
