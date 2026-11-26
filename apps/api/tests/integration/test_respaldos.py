"""Respaldo real con pg_dump contra la base local (almacenamiento simulado) y endpoints del panel."""

import os
import shutil
import subprocess
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import text

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.main import app
from app.services import respaldos
from app.workers.celery_app import celery_app
from tests.integration.conftest import Mundo

pytestmark = pytest.mark.integration


class StorageFalso:
    def __init__(self) -> None:
        self.objetos: dict[str, int] = {}
        self.subidos: list[Path] = []

    def upload(self, src: Path, key: str, content_type: str = "") -> None:
        self.objetos[key] = src.stat().st_size
        copia = Path(f"/tmp/{uuid.uuid4().hex}.dump")  # noqa: S108 - prueba local
        shutil.copy(src, copia)
        self.subidos.append(copia)

    def list_keys(self, prefix: str) -> list[str]:
        return [k for k in self.objetos if k.startswith(prefix)]

    def list_objects(self, prefix: str) -> list[tuple[str, int, datetime]]:
        return [(k, t, datetime.now(UTC)) for k, t in self.objetos.items() if k.startswith(prefix)]

    def delete_many(self, keys: list[str]) -> None:
        for k in keys:
            self.objetos.pop(k, None)

    def object_size(self, key: str) -> int | None:
        return self.objetos.get(key)

    def presign_get(self, key: str, filename: str, content_type: str = "") -> str:
        return f"https://almacen.test/{key}?firma=x"


@pytest.fixture
def storage(monkeypatch: pytest.MonkeyPatch) -> StorageFalso:
    s = StorageFalso()
    monkeypatch.setattr(respaldos, "get_storage", lambda: s)
    monkeypatch.setattr("app.api.v1.plataforma.get_storage", lambda: s)
    return s


@pytest.mark.skipif(not shutil.which("pg_dump"), reason="pg_dump no está instalado")
def test_respaldo_real_se_puede_restaurar(storage: StorageFalso) -> None:
    if not os.environ.get("MIGRATIONS_DATABASE_URL"):
        pytest.skip("MIGRATIONS_DATABASE_URL no configurada")
    # Día 1 del mes: además del diario queda el mensual
    resumen = respaldos.crear_respaldo(datetime(2026, 12, 1, 8, 0, tzinfo=UTC))
    assert resumen["clave"] == "respaldos/diarios/ph-2026-12-01-0300.dump"
    assert resumen["mensual"] == "respaldos/mensuales/ph-2026-12.dump"
    assert set(storage.objetos) == {resumen["clave"], resumen["mensual"]}
    assert int(resumen["tablas"]) > 50 and int(resumen["tamano_bytes"]) > 10_000  # type: ignore[call-overload]
    # El archivo trae los datos de las tablas protegidas por RLS (el rol dueño las ignora)
    cmd = ["pg_restore", "--list", str(storage.subidos[0])]
    listado = subprocess.run(cmd, capture_output=True, text=True, check=True)  # noqa: S603
    for tabla in ("tenants", "users", "units", "pagos_cartera", "asamblea_votos"):
        assert f"TABLE DATA public {tabla} " in listado.stdout, tabla
    for f in storage.subidos:
        f.unlink(missing_ok=True)


def test_respaldo_con_credenciales_malas_no_las_revela(storage: StorageFalso, monkeypatch: pytest.MonkeyPatch) -> None:
    if not shutil.which("pg_dump"):
        pytest.skip("pg_dump no está instalado")
    url = "postgresql+psycopg://alguien:Clave-Muy-Secreta-123@postgres:5432/noexiste"
    monkeypatch.setattr(respaldos, "get_settings", lambda: type("S", (), {"migrations_database_url": url})())
    with pytest.raises(respaldos.RespaldoError) as e:
        respaldos.crear_respaldo()
    assert "Clave-Muy-Secreta-123" not in str(e.value) and "alguien" not in str(e.value)
    assert storage.objetos == {}


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


async def test_panel_de_respaldos(
    http: httpx.AsyncClient, mundo: Mundo, storage: StorageFalso, monkeypatch: pytest.MonkeyPatch
) -> None:
    tareas: list[tuple[str, Any]] = []
    monkeypatch.setattr(celery_app, "send_task", lambda n, args=None, kwargs=None, **_: tareas.append((n, kwargs)))
    dueno = (
        await mundo.db.execute(
            text(
                "INSERT INTO users (email, full_name, password_hash, is_platform_admin) "
                "VALUES (:e, 'Dueño', :h, true) RETURNING id"
            ),
            {"e": f"{uuid.uuid4().hex[:8]}@ejemplo.co", "h": hash_password("Clave-Segura-2026")},
        )
    ).scalar_one()
    h = {"Authorization": f"Bearer {create_access_token(dueno)[0]}"}
    otro = {"Authorization": f"Bearer {create_access_token(mundo.usuarios['ADMIN'])[0]}"}

    vacio = (await http.get("/api/v1/plataforma/respaldos", headers=h)).json()
    assert vacio == {"respaldos": [], "ultimo": None, "al_dia": False}
    assert (await http.get("/api/v1/plataforma/respaldos", headers=otro)).status_code == 404

    storage.objetos["respaldos/diarios/ph-2026-11-26-0300.dump"] = 2_500_000
    lista = (await http.get("/api/v1/plataforma/respaldos", headers=h)).json()
    assert lista["al_dia"] is True and lista["respaldos"][0]["tamano_bytes"] == 2_500_000

    assert (await http.post("/api/v1/plataforma/respaldos", headers=h)).status_code == 202
    assert tareas == [("respaldos.diario", {"forzar": True})]

    ok = await http.post(
        "/api/v1/plataforma/respaldos/descargar", json={"clave": "respaldos/diarios/ph-2026-11-26-0300.dump"}, headers=h
    )
    assert ok.status_code == 200 and ok.json()["url"].startswith("https://almacen.test/")
    for clave in ("tenants/x/documents/y.pdf", "respaldos/diarios/ph-2020-01-01-0300.dump"):
        r = await http.post("/api/v1/plataforma/respaldos/descargar", json={"clave": clave}, headers=h)
        assert r.status_code in (404, 422), clave


async def test_alerta_de_prueba(http: httpx.AsyncClient, mundo: Mundo, monkeypatch: pytest.MonkeyPatch) -> None:
    enviados: list[BaseException] = []
    monkeypatch.setattr("app.api.v1.plataforma.sentry_sdk.capture_exception", enviados.append)
    monkeypatch.setattr("app.api.v1.plataforma.sentry_sdk.flush", lambda *_: None)
    dueno = (
        await mundo.db.execute(
            text(
                "INSERT INTO users (email, full_name, password_hash, is_platform_admin) VALUES (:e, 'D', 'x', true) RETURNING id"
            ),
            {"e": f"{uuid.uuid4().hex[:8]}@ejemplo.co"},
        )
    ).scalar_one()
    h = {"Authorization": f"Bearer {create_access_token(dueno)[0]}"}
    sin = (await http.post("/api/v1/plataforma/probar-alerta", headers=h)).json()
    assert sin["activas"] is False and enviados == []
    monkeypatch.setattr(
        "app.api.v1.plataforma.get_settings", lambda: type("S", (), {"sentry_dsn": "https://x@sentry.test/1"})()
    )
    con = (await http.post("/api/v1/plataforma/probar-alerta", headers=h)).json()
    assert con["activas"] is True and len(enviados) == 1
    otro = {"Authorization": f"Bearer {create_access_token(mundo.usuarios['ADMIN'])[0]}"}
    assert (await http.post("/api/v1/plataforma/probar-alerta", headers=otro)).status_code == 404
