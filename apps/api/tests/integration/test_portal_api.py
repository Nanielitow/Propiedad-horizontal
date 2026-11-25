"""API del portal por HTTP: PQRS de punta a punta, circulares, reservas, inicio y avisos encolados."""

from collections.abc import AsyncIterator
from datetime import timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from redis.asyncio import Redis

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.security import create_access_token
from app.db.rls import set_rls_context
from app.main import app
from app.services.comun import hoy_bogota
from app.workers.celery_app import celery_app
from tests.integration.conftest import Mundo

pytestmark = pytest.mark.integration
HOY = hoy_bogota()


class Cliente:
    def __init__(self, http: httpx.AsyncClient, mundo: Mundo) -> None:
        self.http = http
        self.mundo = mundo
        self.base = f"/api/v1/tenants/{mundo.tenant}"

    def _auth(self, quien: str) -> dict[str, str]:
        token, _ = create_access_token(self.mundo.usuarios[quien])
        return {"Authorization": f"Bearer {token}"}

    async def get(self, quien: str, ruta: str, **params: Any) -> httpx.Response:
        return await self.http.get(self.base + ruta, params=params, headers=self._auth(quien))

    async def post(self, quien: str, ruta: str, body: dict[str, Any] | None = None) -> httpx.Response:
        return await self.http.post(self.base + ruta, json=body or {}, headers=self._auth(quien))

    async def patch(self, quien: str, ruta: str, body: dict[str, Any]) -> httpx.Response:
        return await self.http.patch(self.base + ruta, json=body, headers=self._auth(quien))


@pytest.fixture
def tareas(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, list[Any]]]:
    enviadas: list[tuple[str, list[Any]]] = []
    monkeypatch.setattr(celery_app, "send_task", lambda nombre, args=None, **_: enviadas.append((nombre, args or [])))
    return enviadas


@pytest.fixture
async def api(mundo: Mundo, sin_limites: None, tareas: list[Any]) -> AsyncIterator[Cliente]:
    for clave in ("ANA", "BETO", "CONSEJO"):
        await mundo.usuario(clave, "CONSEJO" if clave == "CONSEJO" else "RESIDENTE")
    await set_rls_context(mundo.db, tenant_id=mundo.tenant, role="SYSTEM")

    async def _db() -> AsyncIterator[Any]:
        yield mundo.db

    app.dependency_overrides[get_db] = _db
    app.state.redis = Redis.from_url(get_settings().redis_url)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
            c = Cliente(http, mundo)
            # Unidades 1-101 (Ana) y 1-102 (Beto), y el salón social con reglas
            for numero, quien in (("101", "ANA"), ("102", "BETO")):
                u = (await c.post("ADMIN", "/unidades", {"tower": "1", "number": numero, "coefficient": "50"})).json()
                r = await c.post(
                    "ADMIN",
                    f"/unidades/{u['id']}/vinculos",
                    {
                        "relacion": "PROPIETARIO",
                        "reside": True,
                        "persona": {
                            "nombre_completo": f"Persona {quien.title()}",
                            "email": f"{quien.lower()}@correo.demo",
                            "user_id": str(mundo.usuarios[quien]),
                        },
                    },
                )
                assert r.status_code == 201, r.text
                c.__dict__[numero] = u["id"]
            z = await c.post(
                "ADMIN",
                "/recaudos/zonas",
                {"nombre": "Salón social", "tarifa_alquiler": "150000", "tarifa_aseo": "50000"},
            )
            assert z.status_code == 201, z.text
            c.__dict__["zona"] = z.json()["id"]
            r = await c.patch(
                "ADMIN", f"/portal/zonas/{c.__dict__['zona']}", {"capacidad": 40, "requiere_paz_y_salvo": False}
            )
            assert r.status_code == 200, r.text
            yield c
    finally:
        app.dependency_overrides.clear()
        await app.state.redis.aclose()


async def test_pqrs_de_punta_a_punta(api: Cliente, tareas: list[tuple[str, list[Any]]]) -> None:
    r = await api.post(
        "ANA",
        "/portal/pqrs",
        {
            "tipo": "QUEJA",
            "categoria": "CONVIVENCIA",
            "asunto": "Ruido nocturno",
            "descripcion": "Fiesta hasta las 3 a. m. en el piso de arriba",
            "unidad_id": api.__dict__["101"],
        },
    )
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["radicado"].startswith("PQRS-") and p["estado"] == "RADICADA" and p["dias_habiles_restantes"] == 15
    assert ("portal.pqrs_radicada", [str(api.mundo.tenant), p["id"]]) in tareas

    assert [x["id"] for x in (await api.get("ANA", "/portal/pqrs")).json()] == [p["id"]]
    assert (await api.get("BETO", "/portal/pqrs")).json() == []  # Beto no ve la queja de Ana
    assert (await api.get("BETO", f"/portal/pqrs/{p['id']}")).status_code == 404

    await api.post(
        "AUXILIAR", f"/portal/pqrs/{p['id']}/mensajes", {"texto": "Revisar cámaras del piso 2", "interno": True}
    )
    r = await api.post(
        "AUXILIAR",
        f"/portal/pqrs/{p['id']}/responder",
        {"texto": "Se envió el llamado de atención escrito al apartamento"},
    )
    assert r.json()["estado"] == "RESPONDIDA"
    assert any(n == "portal.pqrs_respondida" for n, _ in tareas)

    vista_ana = (await api.get("ANA", f"/portal/pqrs/{p['id']}")).json()
    assert [m["interno"] for m in vista_ana["hilo"]] == [False]  # la nota interna no aparece
    assert vista_ana["hilo"][0]["autor"] == "Administración" and vista_ana["hilo"][0]["es_respuesta"]
    r = await api.post(
        "ANA", f"/portal/pqrs/{p['id']}/calificar", {"calificacion": 5, "comentario": "Rápidos y amables"}
    )
    assert r.json()["estado"] == "CERRADA" and r.json()["calificacion"] == 5

    resumen = (await api.get("ADMIN", "/portal/pqrs/resumen")).json()
    assert resumen["por_estado"] == {"CERRADA": 1} and resumen["satisfaccion_promedio"] == "5.0"
    assert (await api.get("CONSEJO", f"/portal/pqrs/{p['id']}")).status_code == 200  # el consejo la consulta
    r = await api.post("CONSEJO", f"/portal/pqrs/{p['id']}/mensajes", {"texto": "hola"})
    assert r.status_code in (400, 403)


async def test_circulares(api: Cliente, tareas: list[tuple[str, list[Any]]]) -> None:
    r = await api.post(
        "AUXILIAR",
        "/portal/circulares",
        {
            "titulo": "Fumigación",
            "cuerpo": "El sábado se fumigarán las zonas comunes de 8 a 10 a. m.",
            "importante": True,
        },
    )
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["estado"] == "BORRADOR" and c["numero"] is None
    assert (await api.get("ANA", "/portal/circulares")).json() == []  # el borrador no se ve
    assert (await api.post("AUXILIAR", f"/portal/circulares/{c['id']}/publicar")).status_code == 403  # publica el admin
    r = await api.post("ADMIN", f"/portal/circulares/{c['id']}/publicar")
    assert r.json()["estado"] == "PUBLICADA" and r.json()["numero"]
    assert ("portal.circular_publicada", [str(api.mundo.tenant), c["id"]]) in tareas

    ana = (await api.get("ANA", "/portal/circulares")).json()
    assert [x["leida"] for x in ana] == [False] and ana[0]["lecturas"] is None  # el residente no ve estadísticas
    assert (await api.post("ANA", f"/portal/circulares/{c['id']}/leida")).status_code == 204
    admin = (await api.get("ADMIN", f"/portal/circulares/{c['id']}")).json()
    assert admin["lecturas"] == 1 and admin["destinatarios_con_cuenta"] == 2
    r = await api.patch("ADMIN", f"/portal/circulares/{c['id']}", {"titulo": "Otro"})
    assert r.status_code == 400 and "aclaración" in r.json()["detail"]


async def test_reservas_e_inicio(api: Cliente, tareas: list[tuple[str, list[Any]]]) -> None:
    fecha = (HOY + timedelta(days=12)).isoformat()
    zonas = (await api.get("ANA", "/portal/zonas")).json()
    assert [z["nombre"] for z in zonas] == ["Salón social"] and zonas[0]["capacidad"] == 40
    r = await api.post(
        "ANA",
        "/portal/reservas",
        {
            "zona_id": api.__dict__["zona"],
            "unidad_id": api.__dict__["101"],
            "fecha_evento": fecha,
            "hora_inicio": "15:00",
            "hora_fin": "21:00",
            "numero_asistentes": 25,
        },
    )
    assert r.status_code == 201, r.text
    res = r.json()
    assert res["estado"] == "SOLICITADA" and Decimal(res["tarifa_total"]) == 200000
    assert any(n == "portal.reserva_solicitada" for n, _ in tareas)

    ocupado = (
        await api.get("BETO", f"/portal/zonas/{api.__dict__['zona']}/disponibilidad", desde=fecha, hasta=fecha)
    ).json()
    assert ocupado == [{"fecha_evento": fecha, "hora_inicio": "15:00:00", "hora_fin": "21:00:00", "propia": False}]
    r = await api.post(
        "BETO",
        "/portal/reservas",
        {
            "zona_id": api.__dict__["zona"],
            "unidad_id": api.__dict__["102"],
            "fecha_evento": fecha,
            "hora_inicio": "20:00",
            "hora_fin": "22:00",
        },
    )
    assert r.status_code == 400 and "ya está reservada" in r.json()["detail"]
    assert (
        await api.post(
            "ADMIN",
            "/portal/reservas",
            {
                "zona_id": api.__dict__["zona"],
                "unidad_id": api.__dict__["102"],
                "fecha_evento": fecha,
                "hora_inicio": "08:00",
                "hora_fin": "10:00",
            },
        )
    ).status_code == 403

    pend = (await api.get("ADMIN", "/portal/pendientes")).json()
    assert pend["reservas_por_decidir"] == 1
    r = await api.post("ADMIN", f"/portal/reservas/{res['id']}/decidir", {"aprobar": False})
    assert r.status_code == 422  # rechazar exige motivo
    r = await api.post("ADMIN", f"/portal/reservas/{res['id']}/decidir", {"aprobar": True})
    assert r.json()["estado"] == "CONFIRMADA"
    assert any(n == "portal.reserva_decidida" for n, _ in tareas)

    inicio = (await api.get("ANA", "/portal/inicio")).json()
    assert inicio["nombre"] == "Ana" and inicio["unidades"] == ["1-101"]
    assert [x["zona"] for x in inicio["proximas_reservas"]] == ["Salón social"]
    assert inicio["saldo_total"] is None  # la copropiedad de prueba no lleva cartera
    assert (await api.get("ADMIN", "/portal/inicio")).status_code == 400
