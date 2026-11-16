"""Contexto de Row Level Security por transacción.

Las políticas RLS leen `app.tenant_id`, `app.user_id` y `app.role`. Se fijan con
`set_config(..., is_local => true)` (equivalente a SET LOCAL): mueren con la
transacción, así que una conexión devuelta al pool nunca arrastra el tenant de
otra petición.

Problema: tras un `commit()` la siguiente transacción empezaría SIN contexto.
Solución: el contexto se guarda en `session.info["rls"]` y un listener
`after_begin` lo re-aplica automáticamente al inicio de cada transacción.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

_SETTINGS = {"tenant_id": "app.tenant_id", "user_id": "app.user_id", "role": "app.role"}
_SET_CONFIG = text("SELECT set_config(:name, :value, true)")

RlsValue = UUID | str


@event.listens_for(Session, "after_begin")
def _apply_rls_context(session: Session, transaction: Any, connection: Any) -> None:
    for key, value in session.info.get("rls", {}).items():
        connection.execute(_SET_CONFIG, {"name": _SETTINGS[key], "value": str(value)})


def _update_info(info: dict[str, Any], values: dict[str, RlsValue | None]) -> dict[str, str]:
    unknown = set(values) - set(_SETTINGS)
    if unknown:
        raise ValueError(f"Claves RLS desconocidas: {unknown}")
    clean = {k: str(v) for k, v in values.items() if v is not None}
    info.setdefault("rls", {}).update(clean)
    return clean


async def set_rls_context(session: AsyncSession, **values: RlsValue | None) -> None:
    clean = _update_info(session.info, values)
    if session.in_transaction():  # si no, after_begin lo aplicará al empezar
        for key, value in clean.items():
            await session.execute(_SET_CONFIG, {"name": _SETTINGS[key], "value": value})


def set_rls_context_sync(session: Session, **values: RlsValue | None) -> None:
    clean = _update_info(session.info, values)
    if session.in_transaction():
        for key, value in clean.items():
            session.execute(_SET_CONFIG, {"name": _SETTINGS[key], "value": value})
