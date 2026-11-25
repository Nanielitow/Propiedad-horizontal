"""API de asambleas por HTTP: de la programación al acta guardada en Documentos."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from redis.asyncio import Redis

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.security import create_access_token
from app.db.rls import set_rls_context
from app.main import app
from app.workers.celery_app import celery_app
from tests.integration.conftest import Mundo

pytestmark = pytest.mark.integration


class Cliente:
    def __init__(self, http: httpx.AsyncClient, mundo: Mundo) -> None:
        self.http = http
        self.mundo = mundo
        self.base = f"/api/v1/tenants/{mundo.tenant}"

    def _auth(self, quien: str) -> dict[str, str]:
        token, _ = create_access_token(self.mundo.usuarios[quien])
        return {"Authorization": f"Bearer {token}"}

    async def get(self, quien: str, ruta: str) -> httpx.Response:
        return await self.http.get(self.base + ruta, headers=self._auth(quien))

    async def post(self, quien: str, ruta: str, body: dict[str, Any] | None = None) -> httpx.Response:
        return await self.http.post(self.base + ruta, json=body or {}, headers=self._auth(quien))


@pytest.fixture
async def api(mundo: Mundo, sin_limites: None, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Cliente]:
    tareas: list[str] = []
    monkeypatch.setattr(
        celery_app, "send_task", lambda nombre, args=None, **_: tareas.append(nombre) or type("R", (), {"id": "x"})()
    )
    guardados: dict[str, bytes] = {}

    class StorageFalso:
        @staticmethod
        def document_key(tenant_id: Any, document_id: Any, name: str) -> str:
            return f"tenants/{tenant_id}/documents/{document_id}/{name}"

        def put_bytes(self, key: str, datos: bytes, _ct: str) -> None:
            guardados[key] = datos

    monkeypatch.setattr("app.services.asambleas.acta.get_storage", lambda: StorageFalso())
    await mundo.usuario("ANA", "RESIDENTE")
    await set_rls_context(mundo.db, tenant_id=mundo.tenant, role="SYSTEM")

    async def _db() -> AsyncIterator[Any]:
        yield mundo.db

    app.dependency_overrides[get_db] = _db
    app.state.redis = Redis.from_url(get_settings().redis_url)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
            c = Cliente(http, mundo)
            c.__dict__["tareas"] = tareas
            c.__dict__["guardados"] = guardados
            for numero, coef in (("101", "40"), ("102", "35"), ("103", "25")):
                u = (await c.post("ADMIN", "/unidades", {"tower": "1", "number": numero, "coefficient": coef})).json()
                persona = {
                    "nombre_completo": f"Propietario {numero}",
                    **({"user_id": str(mundo.usuarios["ANA"])} if numero == "101" else {}),
                }
                await c.post("ADMIN", f"/unidades/{u['id']}/vinculos", {"relacion": "PROPIETARIO", "persona": persona})
                c.__dict__[numero] = u["id"]
            yield c
    finally:
        app.dependency_overrides.clear()
        await app.state.redis.aclose()


async def test_asamblea_completa(api: Cliente) -> None:
    r = await api.post(
        "ADMIN",
        "/asambleas",
        {
            "titulo": "Asamblea extraordinaria: fachada",
            "tipo": "EXTRAORDINARIA",
            "modalidad": "MIXTA",
            "fecha_hora": (datetime.now(UTC) + timedelta(days=5)).isoformat(),
            "lugar": "Salón social",
            "puntos": [
                {"titulo": "Verificación del quórum"},
                {
                    "titulo": "Aprobación de la cuota extraordinaria para la fachada",
                    "tipo": "VOTACION",
                    "mayoria": "CALIFICADA_70",
                },
            ],
        },
    )
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["estado"] == "PROGRAMADA" and [p["titulo"] for p in a["puntos_lista"]][0] == "Verificación del quórum"
    assert a["puntos_lista"][1]["opciones"] == ["Sí", "No", "Abstención"]

    r = await api.post("ADMIN", f"/asambleas/{a['id']}/convocar", {"enviar_correo": True})
    assert r.status_code == 200 and "15 días" in r.json()["aviso"]  # convocada con 5 días
    assert "portal.circular_publicada" in api.__dict__["tareas"]
    assert (
        await api.post(
            "AUXILIAR", f"/asambleas/{a['id']}/abrir", {"presidente": "Elena Vargas", "secretario": "Laura Gómez"}
        )
    ).status_code == 403
    r = await api.post(
        "ADMIN", f"/asambleas/{a['id']}/abrir", {"presidente": "Elena Vargas", "secretario": "Laura Gómez"}
    )
    assert r.json()["estado"] == "EN_CURSO" and r.json()["quorum"]["mensaje"].startswith("Sin quórum")

    # La residente ve solo su unidad en el padrón y asiste desde el portal
    ana = (await api.get("ANA", f"/asambleas/{a['id']}")).json()
    assert [p["etiqueta"] for p in ana["padron"]] == ["1-101"] and ana["puede_asistir_portal"]
    r = await api.post("ANA", f"/asambleas/{a['id']}/asistir")
    assert r.json()["padron"][0]["presente"] and r.json()["padron"][0]["virtual"]
    r = await api.post(
        "AUXILIAR",
        f"/asambleas/{a['id']}/asistencias",
        {
            "unidad_id": api.__dict__["102"],
            "tipo": "APODERADO",
            "asistente_nombre": "Pedro Apoderado",
            "asistente_documento": "79111222",
        },
    )
    d = r.json()
    assert d["quorum"]["hay_quorum"] and d["quorum"]["porcentaje"] == "75.00"

    punto = d["puntos_lista"][1]["id"]
    await api.post("ADMIN", f"/asambleas/puntos/{punto}/abrir")
    r = await api.post("ANA", f"/asambleas/puntos/{punto}/votar", {"opcion": "Sí"})
    assert r.json()["puntos_lista"][1]["mis_votos"] == {"1-101": "Sí"}
    await api.post("AUXILIAR", f"/asambleas/puntos/{punto}/votos", {"unidad_id": api.__dict__["102"], "opcion": "Sí"})
    en_vivo = (await api.get("ADMIN", f"/asambleas/{a['id']}")).json()["puntos_lista"][1]["resultado"]
    assert en_vivo["por_opcion"]["Sí"] == "75.0000" and en_vivo["aprobado"] is True  # 75 % ≥ 70 % del total
    # La residente solo puede leer sus votos y asistencias (RLS), pero ve el mismo quórum y resultado
    vista_ana = (await api.get("ANA", f"/asambleas/{a['id']}")).json()
    assert vista_ana["quorum"]["porcentaje"] == "75.00"
    assert vista_ana["puntos_lista"][1]["resultado"] == en_vivo and vista_ana["puntos_lista"][1]["votos"] == 2
    r = await api.post("ADMIN", f"/asambleas/puntos/{punto}/cerrar")
    assert r.json()["puntos_lista"][1]["estado"] == "CERRADO" and r.json()["puntos_lista"][1]["aprobado"] is True
    await api.post("ADMIN", f"/asambleas/puntos/{d['puntos_lista'][0]['id']}/cerrar")
    r = await api.post("ADMIN", f"/asambleas/{a['id']}/cerrar", {"observaciones": "Sin más asuntos."})
    assert r.json()["estado"] == "CERRADA"

    pdf = await api.get("ADMIN", f"/asambleas/{a['id']}/acta.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    r = await api.post("ADMIN", f"/asambleas/{a['id']}/acta/guardar")
    assert r.status_code == 200 and r.json()["acta_document_id"]
    assert "app.workers.tasks.ingest.ingest_document" in api.__dict__["tareas"]
    assert len(api.__dict__["guardados"]) == 1
    r = await api.post("ADMIN", f"/asambleas/{a['id']}/acta/guardar")
    assert r.status_code == 400  # una sola vez

    lista = (await api.get("ANA", "/asambleas")).json()
    assert lista[0]["estado"] == "CERRADA" and lista[0]["quorum_pct"] == "75.00"
