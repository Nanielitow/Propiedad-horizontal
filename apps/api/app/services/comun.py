"""Piezas de dominio compartidas por los módulos de negocio (recaudos, activos...).

Errores con mensaje apto para el usuario (la API los traduce a 400/403/404/409
en app/api/errores.py), el «actor» que ejecuta un caso de uso y la verificación
de permisos por rol.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import UserRole

TZ = ZoneInfo("America/Bogota")


class ErrorDominio(Exception):
    """Error de negocio con mensaje apto para mostrar al usuario."""


class ValidacionError(ErrorDominio):
    pass


class PermisoDenegado(ErrorDominio):
    pass


class NoEncontrado(ErrorDominio):
    pass


class TransicionInvalida(ErrorDominio):
    pass


class Actor(Protocol):
    """Lo cumple TenantContext de la API; los servicios no dependen de FastAPI."""

    @property
    def tenant_id(self) -> uuid.UUID: ...
    @property
    def user_id(self) -> uuid.UUID: ...
    @property
    def role(self) -> UserRole: ...


@dataclass(frozen=True)
class ActorSimple:
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    role: UserRole


def exigir(actor: Actor, permitidos: frozenset[UserRole], accion: str) -> None:
    if actor.role not in permitidos:
        raise PermisoDenegado(f"Su rol ({actor.role.value}) no permite {accion}")


def hoy_bogota() -> date:
    return datetime.now(TZ).date()


def pesos(valor: Decimal) -> str:
    """Formato colombiano para mensajes: Decimal('1234567.5') -> '$1.234.568'."""
    signo = "-" if valor < 0 else ""
    return f"{signo}${abs(valor):,.0f}".replace(",", ".")


async def fijar_motivo(db: AsyncSession, motivo: str | None) -> None:
    """Motivo que leen los triggers de auditoría (SET LOCAL app.motivo, vive en la transacción)."""
    await db.execute(text("SELECT set_config('app.motivo', :m, true)"), {"m": motivo or ""})
