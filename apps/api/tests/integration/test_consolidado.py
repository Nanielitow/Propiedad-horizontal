"""Panel consolidado: solo las copropiedades donde la persona es administradora, cada una con sus propias cifras."""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import text

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.security import create_access_token
from app.db.rls import set_rls_context
from app.main import app
from tests.integration.conftest import Mundo

pytestmark = pytest.mark.integration


async def _copropiedad(mundo: Mundo, nombre: str, user: uuid.UUID, rol: str) -> uuid.UUID:
    t = uuid.uuid4()
    await mundo.db.execute(
        text("INSERT INTO tenants (id, name, slug) VALUES (:id, :n, :s)"), {"id": t, "n": nombre, "s": f"t-{t}"}
    )
    await set_rls_context(mundo.db, tenant_id=t, role="SYSTEM")
    await mundo.db.execute(
        text("INSERT INTO memberships (tenant_id, user_id, role) VALUES (:t, :u, CAST(:r AS user_role))"),
        {"t": t, "u": user, "r": rol},
    )
    return t


@pytest.fixture
async def http(mundo: Mundo, sin_limites: None) -> AsyncIterator[httpx.AsyncClient]:
    async def _db() -> AsyncIterator[Any]:
        yield mundo.db

    app.dependency_overrides[get_db] = _db
    app.state.redis = Redis.from_url(get_settings().redis_url)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.clear()
        await app.state.redis.aclose()


async def test_resumen_de_varias_copropiedades(http: httpx.AsyncClient, mundo: Mundo) -> None:
    admin = mundo.usuarios["ADMIN"]
    segunda = await _copropiedad(mundo, "Edificio Zeta", admin, "ADMIN")
    await _copropiedad(mundo, "Conjunto Donde Es Recepción", admin, "AUXILIAR")  # no administra: no aparece

    # Una PQRS vencida solo en la segunda copropiedad
    await set_rls_context(mundo.db, tenant_id=segunda, role="SYSTEM")
    await mundo.db.execute(
        text(
            "INSERT INTO pqrs (tenant_id, tipo, categoria, asunto, descripcion, canal, solicitante_nombre, "
            "fecha_limite, radicado_por_id, created_at) VALUES (:t, 'QUEJA', 'ASEO', 'Basuras', "
            "'Shut con malos olores', 'PRESENCIAL', 'Ana', CURRENT_DATE - 2, :u, now() - interval '30 days')"
        ),
        {"t": segunda, "u": admin},
    )

    r = await http.get(
        "/api/v1/mis-copropiedades/resumen", headers={"Authorization": f"Bearer {create_access_token(admin)[0]}"}
    )
    assert r.status_code == 200, r.text
    filas = {c["nombre"]: c for c in r.json()["copropiedades"]}
    assert set(filas) == {"Conjunto de prueba", "Edificio Zeta"}
    assert all(c["errores"] == [] for c in filas.values()), filas
    assert filas["Edificio Zeta"]["pqrs_vencidas"] == 1 and filas["Edificio Zeta"]["pqrs_abiertas"] == 1
    assert filas["Conjunto de prueba"]["pqrs_vencidas"] == 0  # las cifras no se mezclan entre copropiedades

    # Quien no administra ninguna recibe la lista vacía
    aux = mundo.usuarios["AUXILIAR"]
    vacio = await http.get(
        "/api/v1/mis-copropiedades/resumen", headers={"Authorization": f"Bearer {create_access_token(aux)[0]}"}
    )
    assert vacio.json()["copropiedades"] == []
