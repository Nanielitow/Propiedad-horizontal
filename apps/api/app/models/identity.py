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


class User(UUIDPk, CreatedAt, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(unique=True)  # citext en la base
    full_name: Mapped[str]
    password_hash: Mapped[str]
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    last_login_at: Mapped[datetime | None]
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Unit(UUIDPk, Base):
    __tablename__ = "units"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    tower: Mapped[str] = mapped_column(server_default="")
    number: Mapped[str]


class Membership(UUIDPk, CreatedAt, Base):
    __tablename__ = "memberships"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    role: Mapped[UserRole] = mapped_column(pg_enum(UserRole, "user_role"))
    unit_id: Mapped[uuid.UUID | None]
