"""Dependencias de FastAPI: sesión de BD, usuario autenticado y contexto de tenant.

Flujo de una petición a /tenants/{tenant_id}/...:
1. get_db            -> sesión (rol app_user, sin contexto => RLS devuelve 0 filas)
2. get_current_user  -> valida JWT, fija app.user_id
3. get_tenant_context-> verifica la membresía del usuario en ese tenant y fija
                        app.tenant_id + app.role. Desde aquí TODAS las consultas
                        quedan filtradas por RLS en Postgres.
"""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token, token_revoked
from app.db.rls import set_rls_context
from app.db.session import SessionLocal
from app.models import Membership, Tenant, User
from app.models.enums import UserRole

_bearer = HTTPBearer(auto_error=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    # Política: los endpoints que escriben hacen commit EXPLÍCITO antes de
    # responder (y antes de encolar tareas). Lo no confirmado se descarta al cerrar.
    async with SessionLocal() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db)]

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="No autenticado",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None:
        raise _UNAUTHORIZED
    try:
        user_id = decode_access_token(credentials.credentials)
    except jwt.InvalidTokenError as exc:
        raise _UNAUTHORIZED from exc
    user = await db.get(User, user_id)
    if user is None or not user.is_active or token_revoked(credentials.credentials, user.sessions_valid_after):
        raise _UNAUTHORIZED
    await set_rls_context(db, user_id=user.id)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


@dataclass(frozen=True)
class TenantContext:
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    role: UserRole
    is_demo: bool = False  # conjunto de ejemplo: sin invitaciones ni correos reales

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN


async def get_tenant_context(tenant_id: uuid.UUID, user: CurrentUser, db: DbSession) -> TenantContext:
    fila = (
        await db.execute(
            select(Membership.role, Tenant.is_demo)
            .join(Tenant, Tenant.id == Membership.tenant_id)
            .where(Membership.tenant_id == tenant_id, Membership.user_id == user.id, Tenant.deleted_at.is_(None))
        )
    ).first()
    if fila is None:
        # 404 y no 403: no revelar si un edificio existe a quien no pertenece a él
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Copropiedad no encontrada")
    role, is_demo = fila
    await set_rls_context(db, tenant_id=tenant_id, role=role.value)
    return TenantContext(tenant_id=tenant_id, user_id=user.id, role=role, is_demo=is_demo)


TenantCtx = Annotated[TenantContext, Depends(get_tenant_context)]


def require_admin(ctx: TenantCtx) -> TenantContext:
    if not ctx.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requiere rol ADMIN")
    return ctx


AdminCtx = Annotated[TenantContext, Depends(require_admin)]


def require_platform_admin(user: CurrentUser) -> User:
    """Dueño de la plataforma: crea copropiedades y su primer administrador."""
    if not user.is_platform_admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")
    return user


PlatformAdmin = Annotated[User, Depends(require_platform_admin)]
