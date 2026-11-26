"""Conciliación con el extracto por HTTP, sobre los datos de la demo (Los Pinos), en una transacción que se deshace."""

from collections.abc import AsyncIterator
from decimal import Decimal
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


async def test_conciliar_extracto_de_punta_a_punta(http: httpx.AsyncClient, mundo: Mundo) -> None:
    pinos = (await mundo.db.execute(text("SELECT id FROM tenants WHERE slug = 'los-pinos'"))).scalar()
    if pinos is None:
        pytest.skip("Sin los datos de la demo")
    admin = mundo.usuarios["ADMIN"]
    await set_rls_context(mundo.db, tenant_id=pinos, role="SYSTEM")
    await mundo.db.execute(
        text("INSERT INTO memberships (tenant_id, user_id, role) VALUES (:t, :u, 'ADMIN')"), {"t": pinos, "u": admin}
    )
    # Una unidad con un saldo que ninguna otra debe, y el responsable de pago de otra unidad
    unidad = (
        await mundo.db.execute(
            text(
                "WITH s AS (SELECT unidad_id, sum(saldo) AS saldo FROM v_saldos_cargo "
                "  WHERE estado = 'VIGENTE' AND saldo > 0 GROUP BY unidad_id) "
                "SELECT u.id, u.tower, u.number, s.saldo FROM s JOIN units u ON u.id = s.unidad_id "
                "WHERE u.tower <> '' AND (SELECT count(*) FROM s s2 WHERE s2.saldo = s.saldo) = 1 LIMIT 1"
            )
        )
    ).one()
    otra = (
        await mundo.db.execute(
            text(
                "SELECT u.id, p.nombre_completo FROM unidad_personas up JOIN personas p ON p.id = up.persona_id "
                "JOIN units u ON u.id = up.unidad_id WHERE up.responsable_pago AND up.fecha_fin IS NULL "
                "AND u.id <> :u LIMIT 1"
            ),
            {"u": unidad.id},
        )
    ).one()
    valor = f"{Decimal(unidad.saldo):.2f}".replace(".", ",")
    csv = (
        "Fecha;Descripción;Nombre;Valor\n"
        f"2026/11/20;TRANSFERENCIA TORRE {unidad.tower} APTO {unidad.number};;{valor}\n"
        f"2026/11/21;ABONO TRANSFERENCIA;{otra.nombre_completo.upper()};12345\n"
        "2026/11/22;PAGO SIN IDENTIFICAR;;77777\n"
        "2026/11/22;GMF 4X1000;;-4000\n"
    ).encode()
    h = {"Authorization": f"Bearer {create_access_token(admin)[0]}"}
    base = f"/api/v1/tenants/{pinos}/cartera/extracto"

    r = await http.post(f"{base}/analizar", files={"archivo": ("extracto.csv", csv, "text/csv")}, headers=h)
    assert r.status_code == 200, r.text
    movs = r.json()["movimientos"]
    assert len(movs) == 3  # el débito (GMF) no cuenta
    assert movs[0]["unidad_id"] == str(unidad.id) and movs[0]["confianza"] == "alta"
    assert movs[1]["unidad_id"] == str(otra.id) and movs[1]["confianza"] in ("media", "alta")
    assert movs[2]["unidad_id"] is None and movs[2]["confianza"] == "ninguna"
    assert all(m["ya_registrado"] is None for m in movs)

    item = {k: movs[0][k] for k in ("fila", "unidad_id", "valor", "medio_pago", "referencia")}
    item |= {"fecha_pago": movs[0]["fecha"], "pagador_nombre": movs[0]["pagador"]}
    reg = await http.post(f"{base}/registrar", json={"items": [item]}, headers=h)
    assert reg.status_code == 200, reg.text
    assert len(reg.json()["creados"]) == 1 and reg.json()["creados"][0]["recibo"] > 0 and reg.json()["errores"] == []

    # Volver a subir el mismo extracto: ese movimiento sale como ya registrado, y registrarlo otra vez falla
    r2 = await http.post(f"{base}/analizar", files={"archivo": ("extracto.csv", csv, "text/csv")}, headers=h)
    assert r2.json()["movimientos"][0]["ya_registrado"].startswith("Recibo ")
    dup = await http.post(f"{base}/registrar", json={"items": [item]}, headers=h)
    assert dup.json()["creados"] == [] and "ya se registró" in dup.json()["errores"][0]["motivo"]

    # Recepción no puede conciliar
    aux = {"Authorization": f"Bearer {create_access_token(mundo.usuarios['AUXILIAR'])[0]}"}
    await set_rls_context(mundo.db, tenant_id=pinos, role="SYSTEM")
    await mundo.db.execute(
        text("INSERT INTO memberships (tenant_id, user_id, role) VALUES (:t, :u, 'AUXILIAR')"),
        {"t": pinos, "u": mundo.usuarios["AUXILIAR"]},
    )
    prohibido = await http.post(f"{base}/analizar", files={"archivo": ("e.csv", csv, "text/csv")}, headers=aux)
    assert prohibido.status_code == 403
