"""Entorno compartido de los tests de servicio de recaudos.

Una copropiedad nueva con un usuario por rol (y su membresía), sobre una sesión
async como app_user dentro de una transacción que se revierte al final.
"""

import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.db.rls import set_rls_context
from app.models import ConceptoRecaudo
from app.models.enums import UserRole
from app.services.recaudos.dominio import ActorSimple

AHORA = datetime.now(UTC).replace(microsecond=0)
ROLES = ("ADMIN", "AUXILIAR", "CONTABILIDAD")


@dataclass
class Mundo:
    db: AsyncSession
    tenant: uuid.UUID
    usuarios: dict[str, uuid.UUID]

    async def como(self, rol: UserRole, quien: str | None = None) -> ActorSimple:
        """Cambia el contexto RLS de la sesión al usuario `quien` (por defecto, el del rol)."""
        user = self.usuarios[quien or rol.value]
        await set_rls_context(self.db, tenant_id=self.tenant, user_id=user, role=rol.value)
        return ActorSimple(tenant_id=self.tenant, user_id=user, role=rol)

    async def concepto(self, codigo: str) -> ConceptoRecaudo:
        return (await self.db.scalars(select(ConceptoRecaudo).where(ConceptoRecaudo.codigo == codigo))).one()

    async def usuario(self, clave: str, rol: str) -> uuid.UUID:
        """Crea un usuario extra (p. ej. un segundo auxiliar) con su membresía."""
        user = uuid.uuid4()
        await self.db.execute(
            text("INSERT INTO users (id, email, full_name, password_hash) VALUES (:id, :e, :n, 'x')"),
            {"id": user, "e": f"{user}@test.local", "n": clave.title()},
        )
        await set_rls_context(self.db, tenant_id=self.tenant, role="SYSTEM")
        await self.db.execute(
            text("INSERT INTO memberships (tenant_id, user_id, role) VALUES (:t, :u, CAST(:r AS user_role))"),
            {"t": self.tenant, "u": user, "r": rol},
        )
        self.usuarios[clave] = user
        return user


@pytest.fixture
async def mundo() -> AsyncIterator[Mundo]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL no configurada")
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        tx = await conn.begin()
        db = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
        tenant = uuid.uuid4()
        await db.execute(
            text("INSERT INTO tenants (id, name, slug) VALUES (:id, 'Conjunto de prueba', :s)"),
            {"id": tenant, "s": f"test-{tenant}"},
        )
        m = Mundo(db, tenant, {})
        for rol in ROLES:
            await m.usuario(rol, rol)
        await set_rls_context(db, tenant_id=tenant, role="SYSTEM")
        await db.execute(text("SELECT seed_conceptos_recaudo(:t)"), {"t": tenant})
        try:
            yield m
        finally:
            await db.close()
            await tx.rollback()
    await engine.dispose()


@pytest.fixture
def sin_limites(monkeypatch: pytest.MonkeyPatch) -> None:
    """Los tests de API no deben depender de los contadores de uso guardados en Redis
    (en modo demo, ejecuciones anteriores agotarían el límite diario por visitante)."""

    async def _libre(*_: object, **__: object) -> None:
        return None

    monkeypatch.setattr("app.core.rate_limit.hit", _libre)
