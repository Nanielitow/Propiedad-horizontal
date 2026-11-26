import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, UUIDPk
from app.models.enums import UserRole, pg_enum


class Tenant(UUIDPk, CreatedAt, Base):
    __tablename__ = "tenants"

    name: Mapped[str]
    slug: Mapped[str] = mapped_column(unique=True)
    nit: Mapped[str | None]
    address: Mapped[str | None]
    city: Mapped[str | None]
    settings: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())
    deleted_at: Mapped[datetime | None]
    # Conjunto de ejemplo (demo pública): sin invitaciones ni correos a direcciones reales
    is_demo: Mapped[bool] = mapped_column(server_default=text("false"))


class User(UUIDPk, CreatedAt, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(unique=True)  # citext en la base
    full_name: Mapped[str]
    password_hash: Mapped[str | None]  # None = invitado que aún no activa su cuenta
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    is_platform_admin: Mapped[bool] = mapped_column(server_default=text("false"))
    sessions_valid_after: Mapped[datetime | None]  # tokens anteriores dejan de valer
    terms_accepted_at: Mapped[datetime | None]
    terms_version: Mapped[str | None]
    last_login_at: Mapped[datetime | None]
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Membership(UUIDPk, CreatedAt, Base):
    __tablename__ = "memberships"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    role: Mapped[UserRole] = mapped_column(pg_enum(UserRole, "user_role"))
    unit_id: Mapped[uuid.UUID | None]


class AccountToken(UUIDPk, CreatedAt, Base):
    """Enlace de un solo uso (invitación o recuperación de clave). Solo se guarda el SHA-256."""

    __tablename__ = "account_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str]  # INVITACION | RECUPERACION
    token_hash: Mapped[str] = mapped_column(unique=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tenants.id"))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]
