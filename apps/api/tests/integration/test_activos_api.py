"""API de activos y mantenimiento por HTTP: rutas, códigos, permisos y costos por rol."""

from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import select, text

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.security import create_access_token
from app.db.rls import set_rls_context
from app.main import app
from app.models import CategoriaActivo
from app.services.comun import TZ
from app.workers.celery_app import celery_app
from tests.integration.conftest import AHORA, Mundo

pytestmark = pytest.mark.integration
HOY = AHORA.astimezone(TZ).date()


class Cliente:
    def __init__(self, http: httpx.AsyncClient, mundo: Mundo) -> None:
        self.http = http
        self.mundo = mundo
        self.base = f"/api/v1/tenants/{mundo.tenant}/activos"

    def _auth(self, quien: str) -> dict[str, str]:
        token, _ = create_access_token(self.mundo.usuarios[quien])
        return {"Authorization": f"Bearer {token}"}

    async def get(self, quien: str, ruta: str = "", **params: Any) -> httpx.Response:
        return await self.http.get(self.base + ruta, params=params, headers=self._auth(quien))

    async def post(self, quien: str, ruta: str, body: dict[str, Any] | None = None) -> httpx.Response:
        return await self.http.post(self.base + ruta, json=body or {}, headers=self._auth(quien))

    async def patch(self, quien: str, ruta: str, body: dict[str, Any]) -> httpx.Response:
        return await self.http.patch(self.base + ruta, json=body, headers=self._auth(quien))

    async def delete(self, quien: str, ruta: str) -> httpx.Response:
        return await self.http.delete(self.base + ruta, headers=self._auth(quien))


@pytest.fixture
def tareas(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, list[Any]]]:
    enviadas: list[tuple[str, list[Any]]] = []
    monkeypatch.setattr(celery_app, "send_task", lambda nombre, args=None, **_: enviadas.append((nombre, args or [])))
    return enviadas


@pytest.fixture
async def api(mundo: Mundo, sin_limites: None) -> AsyncIterator[Cliente]:
    await mundo.usuario("MANTENIMIENTO", "MANTENIMIENTO")
    await mundo.usuario("CONSEJO", "CONSEJO")
    await set_rls_context(mundo.db, tenant_id=mundo.tenant, role="SYSTEM")
    await mundo.db.execute(text("SELECT seed_categorias_activos(:t)"), {"t": mundo.tenant})

    async def _db() -> AsyncIterator[Any]:
        yield mundo.db

    app.dependency_overrides[get_db] = _db
    app.state.redis = Redis.from_url(get_settings().redis_url)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
            yield Cliente(http, mundo)
    finally:
        app.dependency_overrides.clear()
        await app.state.redis.aclose()


async def nuevo_activo(api: Cliente, nombre: str = "Motobomba principal", **extra: Any) -> dict[str, Any]:
    await set_rls_context(api.mundo.db, tenant_id=api.mundo.tenant, role="SYSTEM")
    categoria = (
        await api.mundo.db.scalars(select(CategoriaActivo.id).where(CategoriaActivo.codigo == "ELECTROMECANICOS"))
    ).one()
    r = await api.post(
        "ADMIN",
        "",
        {"nombre": nombre, "categoria_id": str(categoria), "ubicacion": "Torre 1 · Sótano", "criticidad": "ALTA"}
        | extra,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def plan_aprobado(api: Cliente, activo_id: str, **extra: Any) -> dict[str, Any]:
    body = {"activo_id": activo_id, "nombre": "Revisión mensual", "periodicidad": "MENSUAL", "fecha_inicio": str(HOY)}
    r = await api.post("AUXILIAR", "/planes", body | extra)
    assert r.status_code == 201, r.text
    assert (await api.post("AUXILIAR", f"/planes/{r.json()['id']}/aprobar")).status_code == 403
    r = await api.post("ADMIN", f"/planes/{r.json()['id']}/aprobar")
    assert r.status_code == 200, r.text
    return r.json()


async def test_hoja_de_vida_y_buscador(api: Cliente) -> None:
    a = await nuevo_activo(api, especificaciones={"Potencia": "15 HP"}, vida_util_anios=20)
    assert a["codigo_interno"] == "ACT-001"
    assert a["qr_url"].endswith(f"/activos/qr/{a['qr_token']}")
    assert a["puede_ver_costos"] is True and a["semaforo"] is None

    sin_permiso = await api.post(
        "MANTENIMIENTO", "", {"nombre": "X1", "categoria_id": a["categoria"]["id"], "ubicacion": "Lobby"}
    )
    assert sin_permiso.status_code == 403
    assert (await api.get("CONSEJO", "")).status_code == 403  # el consejo verá consolidados (fase 5)

    plan = await plan_aprobado(api, a["id"])
    assert plan["aprobado"] and plan["proxima_fecha"] == str(HOY)
    pagina = (await api.get("MANTENIMIENTO", "", texto="motobomba")).json()
    assert pagina["total"] == 1 and pagina["items"][0]["semaforo"] == "AMARILLO"  # vence hoy
    assert pagina["por_semaforo"]["AMARILLO"] == 1
    assert (await api.get("ADMIN", "", semaforo="ROJO")).json()["total"] == 0

    hoja = (await api.get("MANTENIMIENTO", f"/{a['id']}")).json()
    assert hoja["puede_ver_costos"] is False and hoja["costo_acumulado"] is None
    assert len(hoja["proximas_actividades"]) == 12 and hoja["planes"][0]["nombre"] == "Revisión mensual"

    r = await api.patch("AUXILIAR", f"/{a['id']}", {"marca": "Pedrollo", "motivo": "Dato de la placa del equipo"})
    assert r.status_code == 200 and r.json()["marca"] == "Pedrollo"
    eventos = (await api.get("ADMIN", f"/auditoria/activo/{a['id']}")).json()
    assert {e["accion"] for e in eventos} >= {"CREACION", "EDICION"}
    assert any(e["motivo"] == "Dato de la placa del equipo" for e in eventos)


async def test_calendario_reprogramacion_y_asignacion(api: Cliente) -> None:
    a = await nuevo_activo(api)
    await plan_aprobado(api, a["id"])
    actividades = (await api.get("ADMIN", "/actividades", desde=str(HOY), hasta=str(HOY + timedelta(days=95)))).json()
    assert len(actividades) == 4  # hoy y los tres meses siguientes
    primera = actividades[0]

    assert (
        await api.post(
            "MANTENIMIENTO",
            f"/actividades/{primera['id']}/reprogramar",
            {"nueva_fecha": str(HOY + timedelta(days=3)), "motivo": "Lo pide el técnico"},
        )
    ).status_code == 403
    r = await api.post(
        "AUXILIAR",
        f"/actividades/{primera['id']}/reprogramar",
        {"nueva_fecha": str(HOY + timedelta(days=3)), "motivo": "El contratista no puede hoy"},
    )
    assert r.status_code == 200 and r.json()["reprogramada"] is True
    historial = (await api.get("ADMIN", f"/actividades/{primera['id']}/reprogramaciones")).json()
    assert historial[0]["motivo"] == "El contratista no puede hoy"

    tecnico = str(api.mundo.usuarios["MANTENIMIENTO"])
    r = await api.post("ADMIN", f"/actividades/{primera['id']}/asignar", {"asignado_a_id": tecnico})
    assert r.json()["asignado_a"]["id"] == tecnico
    assert [x["id"] for x in (await api.get("MANTENIMIENTO", "/actividades", mias=True)).json()] == [primera["id"]]


async def test_mantenimiento_oculta_costos_a_quien_no_debe_verlos(api: Cliente) -> None:
    a = await nuevo_activo(api)
    await plan_aprobado(api, a["id"])
    [act] = (await api.get("MANTENIMIENTO", "/actividades", activo_id=a["id"], hasta=str(HOY), desde=str(HOY))).json()
    body = {
        "activo_id": a["id"],
        "actividad_id": act["id"],
        "tipo": "PREVENTIVO",
        "fecha_ejecucion": str(HOY),
        "nombre_tecnico": "Pedro Ramírez",
        "actividades_realizadas": "Limpieza y ajuste de sellos",
        "estado_post_intervencion": "OPERATIVO",
        "costo_mano_obra": "150000",
        "costo_repuestos": "40000",
        "recomendaciones": [
            {"descripcion": "Cambiar rodamientos en 6 meses", "prioridad": "ALTA", "costo_estimado": "300000"}
        ],
    }
    r = await api.post("MANTENIMIENTO", "/mantenimientos", body)
    assert r.status_code == 201, r.text
    mto = r.json()
    assert mto["codigo"] == "MTO-0001" and mto["costo_total"] is None  # el técnico registra costos pero no los consulta
    assert mto["recomendaciones"][0]["costo_estimado"] is None

    admin = (await api.get("ADMIN", f"/mantenimientos/{mto['id']}")).json()
    assert admin["costo_total"] == "190000.00" and admin["plan"]["nombre"] == "Revisión mensual"
    conta = (await api.get("CONTABILIDAD", f"/{a['id']}")).json()
    assert conta["costo_acumulado"] == "190000.00"
    auxiliar = (await api.get("AUXILIAR", "/recomendaciones", pendientes=True)).json()
    assert auxiliar[0]["costo_estimado"] is None and auxiliar[0]["mantenimiento_origen"]["nombre"] == "MTO-0001"

    # La actividad ya está cumplida (409) y el historial no se edita: solo se anula
    assert (await api.post("MANTENIMIENTO", "/mantenimientos", body)).status_code == 409
    assert (
        await api.post("AUXILIAR", f"/mantenimientos/{mto['id']}/anular", {"motivo": "Registro en activo equivocado"})
    ).status_code == 403
    r = await api.post("ADMIN", f"/mantenimientos/{mto['id']}/anular", {"motivo": "Registro en activo equivocado"})
    assert r.status_code == 200 and r.json()["anulado"] is True
    assert (await api.get("ADMIN", f"/actividades/{act['id']}")).json()["estado"] == "PROGRAMADA"


async def test_novedad_critica_avisa_y_sigue_su_flujo(api: Cliente, tareas: list[tuple[str, list[Any]]]) -> None:
    a = await nuevo_activo(api, "Ascensor torre 1")
    r = await api.post(
        "MANTENIMIENTO",
        "/novedades",
        {
            "activo_id": a["id"],
            "descripcion": "Ascensor detenido entre pisos",
            "prioridad": "CRITICA",
            "riesgo_identificado": "Personas atrapadas",
        },
    )
    assert r.status_code == 201, r.text
    nov = r.json()
    assert nov["codigo"] == "NOV-0001" and nov["estado"] == "REPORTADA" and nov["horas_sin_atender"] == 0
    assert tareas == [("activos.novedad_critica", [str(api.mundo.tenant), nov["id"]])]

    assert (await api.post("ADMIN", f"/novedades/{nov['id']}/estado", {"estado": "CERRADA"})).status_code == 409
    r = await api.post(
        "AUXILIAR",
        f"/novedades/{nov['id']}/estado",
        {"estado": "EN_GESTION", "asignado_a_id": str(api.mundo.usuarios["MANTENIMIENTO"])},
    )
    assert r.status_code == 200 and r.json()["fecha_atencion"] is not None
    r = await api.post(
        "MANTENIMIENTO", f"/novedades/{nov['id']}/estado", {"estado": "EN_EJECUCION", "diagnostico": "Falla del freno"}
    )
    assert r.status_code == 200
    r = await api.post("ADMIN", f"/novedades/{nov['id']}/estado", {"estado": "CERRADA"})
    assert r.status_code == 400 and "solución" in r.json()["detail"]
    r = await api.post(
        "ADMIN", f"/novedades/{nov['id']}/estado", {"estado": "CERRADA", "solucion_implementada": "Ajuste del freno"}
    )
    assert r.json()["estado"] == "CERRADA"
    assert (await api.get("ADMIN", "/novedades", abiertas=True)).json() == []


async def test_qr_etiquetas_y_regeneracion(api: Cliente) -> None:
    a = await nuevo_activo(api)
    await nuevo_activo(api, "Planta eléctrica")
    vista = (await api.get("MANTENIMIENTO", f"/qr/{a['qr_token']}")).json()
    assert vista["codigo_interno"] == "ACT-001" and vista["novedades_abiertas"] == []
    assert (await api.get("MANTENIMIENTO", "/qr/token-que-no-existe")).status_code == 404

    svg = await api.get("ADMIN", f"/{a['id']}/qr.svg")
    assert svg.headers["content-type"].startswith("image/svg+xml") and svg.text.startswith("<svg")
    pdf = await api.get("AUXILIAR", "/etiquetas.pdf")
    assert pdf.headers["content-type"] == "application/pdf" and pdf.content[:4] == b"%PDF"

    nuevo = (await api.post("ADMIN", f"/{a['id']}/qr/regenerar")).json()["qr_token"]
    assert nuevo != a["qr_token"]
    assert (await api.get("MANTENIMIENTO", f"/qr/{a['qr_token']}")).status_code == 404  # la etiqueta vieja ya no sirve


async def test_baja_y_errores_de_la_base_traducidos(api: Cliente) -> None:
    a = await nuevo_activo(api)
    assert (
        await api.post("AUXILIAR", f"/{a['id']}/baja", {"motivo": "Equipo reemplazado por uno nuevo"})
    ).status_code == 403
    r = await api.post("ADMIN", f"/{a['id']}/baja", {"motivo": "Equipo reemplazado por uno nuevo"})
    assert r.status_code == 200 and r.json()["estado"] == "DADO_DE_BAJA"
    assert (await api.get("ADMIN", "")).json()["total"] == 0  # el buscador oculta las bajas
    assert (await api.get("ADMIN", "", incluir_bajas=True)).json()["total"] == 1
    r = await api.patch("ADMIN", f"/{a['id']}", {"ubicacion": "Otra", "motivo": "Cambio de ubicación"})
    assert r.status_code == 400 and "dado de baja" in r.json()["detail"]
    assert (await api.get("ADMIN", f"/{a['id']}/lecturas")).json() == []
