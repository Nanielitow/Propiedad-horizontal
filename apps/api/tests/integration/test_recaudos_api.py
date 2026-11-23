"""API de recaudos por HTTP: rutas, códigos de error, permisos y respuestas.

Usa la sesión con rollback de conftest (get_db sobrescrito), tokens reales y
captura los envíos a Celery en lugar de encolarlos.
"""

import uuid
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
from app.main import app
from app.models.enums import UserRole
from app.workers.celery_app import celery_app
from tests.integration.conftest import AHORA, Mundo

pytestmark = pytest.mark.integration


class Cliente:
    def __init__(self, http: httpx.AsyncClient, mundo: Mundo) -> None:
        self.http = http
        self.mundo = mundo
        self.base = f"/api/v1/tenants/{mundo.tenant}/recaudos"

    def _auth(self, quien: str) -> dict[str, str]:
        token, _ = create_access_token(self.mundo.usuarios[quien])
        return {"Authorization": f"Bearer {token}"}

    async def get(self, quien: str, ruta: str = "", **params: Any) -> httpx.Response:
        return await self.http.get(self.base + ruta, params=params, headers=self._auth(quien))

    async def post(self, quien: str, ruta: str, body: dict[str, Any] | None = None) -> httpx.Response:
        return await self.http.post(self.base + ruta, json=body or {}, headers=self._auth(quien))

    async def patch(self, quien: str, ruta: str, body: dict[str, Any]) -> httpx.Response:
        return await self.http.patch(self.base + ruta, json=body, headers=self._auth(quien))

    async def concepto(self, codigo: str) -> str:
        return str((await self.mundo.concepto(codigo)).id)


@pytest.fixture
def tareas(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, list[Any]]]:
    enviadas: list[tuple[str, list[Any]]] = []
    monkeypatch.setattr(celery_app, "send_task", lambda nombre, args=None, **_: enviadas.append((nombre, args or [])))
    return enviadas


@pytest.fixture
async def api(mundo: Mundo, sin_limites: None) -> AsyncIterator[Cliente]:
    for clave, rol in (("CONSEJO", "CONSEJO"), ("AUXILIAR2", "AUXILIAR")):
        await mundo.usuario(clave, rol)

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


def parqueadero(concepto: str, minutos: int = 61, placa: str = "abc-123") -> dict[str, Any]:
    return {
        "concepto_id": concepto,
        "medio_pago": "EFECTIVO",
        "nombre_pagador": "Visitante",
        "parqueadero": {
            "placa_vehiculo": placa,
            "hora_ingreso": (AHORA - timedelta(minutes=minutos)).isoformat(),
            "hora_salida": AHORA.isoformat(),
        },
    }


async def test_flujo_de_caja_con_alerta_por_http(api: Cliente, tareas: list[tuple[str, list[Any]]]) -> None:
    r = await api.post("AUXILIAR", "", parqueadero(await api.concepto("PARQUEADERO")))
    assert r.status_code == 201, r.text
    recaudo = r.json()
    assert (recaudo["consecutivo"], recaudo["valor_recibido"], recaudo["placa"]) == (1, "4000.00", "ABC123")
    assert recaudo["parqueadero"]["minutos_totales"] == 61
    assert [i["valor"] for i in recaudo["items"]] == ["4000.00"]

    estado = (await api.get("AUXILIAR", "/caja/estado")).json()
    assert (estado["cantidad"], estado["total_efectivo"]) == (1, "4000.00")

    r = await api.post("AUXILIAR", "/caja/cierres", {"valor_fisico_contado": 3000})
    assert r.status_code == 400
    assert "faltante de $1.000" in r.json()["detail"]
    r = await api.post(
        "AUXILIAR",
        "/caja/cierres",
        {"valor_fisico_contado": 3000, "observacion_justificacion": "Se dio mal un cambio al visitante"},
    )
    assert r.status_code == 201, r.text
    assert (r.json()["tipo_diferencia"], r.json()["cantidad_recaudos"]) == ("FALTANTE", 1)

    # El correo de la alerta se encola después del commit
    [(nombre, args)] = tareas
    assert nombre == "recaudos.notificar_alertas"
    alertas = (await api.get("ADMIN", "/alertas")).json()
    assert [a["id"] for a in alertas] == args[1]
    assert alertas[0]["tipo"] == "DIFERENCIA_CIERRE"


async def test_permisos_por_rol_y_codigos_http(api: Cliente, tareas: list[tuple[str, list[Any]]]) -> None:
    rid = (await api.post("AUXILIAR", "", parqueadero(await api.concepto("PARQUEADERO")))).json()["id"]

    assert (await api.get("CONSEJO", "")).status_code == 403  # el consejo no ve el detalle
    assert (await api.get("AUXILIAR2", f"/{rid}")).status_code == 404  # recaudo de otro auxiliar: invisible
    r = await api.post("AUXILIAR", f"/{rid}/anular", {"motivo": "Me equivoqué de concepto"})
    assert r.status_code == 403
    assert "no permite anular" in r.json()["detail"]

    r = await api.post("ADMIN", f"/{rid}/anular", {"motivo": "Registro duplicado por error"})
    assert (r.status_code, r.json()["estado"]) == (200, "ANULADO")
    assert (await api.post("ADMIN", f"/{rid}/anular", {"motivo": "Registro duplicado por error"})).status_code == 409
    assert (await api.post("ADMIN", f"/{rid}/anular", {"motivo": "corto"})).status_code == 422

    historial = (await api.get("CONTABILIDAD", f"/{rid}/auditoria")).json()
    assert [h["accion"] for h in historial] == ["CREACION", "ANULACION"]
    assert historial[-1]["motivo"] == "Registro duplicado por error"
    assert tareas == []  # anular algo aún en caja no genera alerta


async def test_validaciones_de_dominio_responden_400(api: Cliente) -> None:
    sin_placa = {"concepto_id": await api.concepto("PARQUEADERO"), "medio_pago": "EFECTIVO", "nombre_pagador": "X Y"}
    r = await api.post("AUXILIAR", "", sin_placa)
    assert (r.status_code, "placa" in r.json()["detail"]) == (400, True)
    transferencia = {
        "concepto_id": await api.concepto("OTROS"),
        "medio_pago": "TRANSFERENCIA",
        "nombre_pagador": "Apto 301",
        "valor_recibido": "80000",
    }
    assert (await api.post("ADMIN", "", transferencia)).status_code == 400  # sin comprobante
    assert (await api.post("CONTABILIDAD", "", transferencia | {"numero_comprobante": "T-1"})).status_code == 403


async def test_buscador_filtra_pagina_y_suma_sin_anulados(api: Cliente) -> None:
    parq = await api.concepto("PARQUEADERO")
    await api.post("AUXILIAR", "", parqueadero(parq, 61, "ABC123"))
    await api.post("AUXILIAR", "", parqueadero(parq, 30, "XYZ987"))
    t = await api.post(
        "ADMIN",
        "",
        {
            "concepto_id": await api.concepto("OTROS"),
            "medio_pago": "TRANSFERENCIA",
            "nombre_pagador": "Andrea Molina",
            "identificacion_pagador": "52123456",
            "valor_recibido": "80000",
            "numero_comprobante": "NEQUI-1",
        },
    )
    await api.post("ADMIN", f"/{t.json()['id']}/anular", {"motivo": "Transferencia duplicada en el banco"})

    todo = (await api.get("ADMIN", "", page_size=2)).json()
    assert (todo["total"], len(todo["items"]), todo["suma"]) == (3, 2, "6000.00")  # 4000 + 2000; la anulada no suma
    assert (await api.get("ADMIN", "", placa="xyz")).json()["total"] == 1
    assert (await api.get("ADMIN", "", pagador="5212")).json()["items"][0]["nombre_pagador"] == "Andrea Molina"
    assert (await api.get("ADMIN", "", medio_pago="EFECTIVO", estado=["RECAUDADO_EN_CAJA"])).json()["total"] == 2
    assert (await api.get("AUXILIAR2", "")).json()["total"] == 0  # RLS: no recibió nada
    assert (await api.get("ADMIN", "", mes=5)).status_code == 400  # mes sin año


async def test_soportes_solo_de_la_propia_copropiedad(api: Cliente) -> None:
    r = await api.post("AUXILIAR", "/soportes/upload-url", {"content_type": "text/html", "size_bytes": 100})
    assert r.status_code == 400
    r = await api.post("AUXILIAR", "/soportes/upload-url", {"content_type": "image/jpeg", "size_bytes": 50_000})
    assert r.status_code == 200
    key = r.json()["soporte_key"]
    assert key.startswith(f"tenants/{api.mundo.tenant}/recaudos/soportes/") and key.endswith(".jpg")

    base = {
        "concepto_id": await api.concepto("OTROS"),
        "medio_pago": "TRANSFERENCIA",
        "nombre_pagador": "Apto 301",
        "valor_recibido": "50000",
    }
    ajeno = f"tenants/{uuid.uuid4()}/recaudos/soportes/{uuid.uuid4()}.jpg"
    assert (await api.post("ADMIN", "", base | {"soporte_key": ajeno})).status_code == 400
    r = await api.post("ADMIN", "", base | {"soporte_key": key})
    assert (r.status_code, r.json()["tiene_soporte"]) == (201, True)
    assert r.json()["soporte_url"].startswith("http")


async def test_dashboard_para_consejo_y_rutas_fijas(api: Cliente) -> None:
    await api.post("AUXILIAR", "", parqueadero(await api.concepto("PARQUEADERO")))
    await api.post(
        "ADMIN",
        "",
        {
            "concepto_id": await api.concepto("OTROS"),
            "medio_pago": "TRANSFERENCIA",
            "nombre_pagador": "Apto 301",
            "valor_recibido": "80000",
            "numero_comprobante": "T-9",
        },
    )
    r = await api.get("CONSEJO", "/dashboard")
    assert r.status_code == 200, r.text
    d = r.json()
    assert Decimal(d["total_mes"]) == Decimal(84000)
    assert Decimal(d["efectivo_en_caja"]) == Decimal(4000)
    assert d["transferencias_pendientes"]["cantidad"] == 1
    assert {c["codigo"] for c in d["por_concepto"]} == {"PARQUEADERO", "OTROS"}
    assert (await api.get("AUXILIAR", "/dashboard")).status_code == 403

    # /entregas, /consignaciones y /alertas no los captura /{recaudo_id}
    assert (await api.get("ADMIN", "/entregas")).json() == []
    assert (await api.get("ADMIN", "/consignaciones")).json() == []
    assert (await api.get("ADMIN", "/consignaciones/pendientes")).json() == []
    assert len((await api.get("AUXILIAR", "/conceptos")).json()) == 4
    assert {p["rol"] for p in (await api.get("AUXILIAR", "/personal", rol="ADMIN")).json()} == {"ADMIN"}


async def test_errores_de_triggers_se_traducen_con_su_mensaje(api: Cliente) -> None:
    """Si una regla la frena la base de datos (no el servicio), el usuario recibe 4xx y un mensaje claro."""
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    from app.api.errores import traducir_error_db

    rid = (await api.post("ADMIN", "", parqueadero(await api.concepto("PARQUEADERO")))).json()["id"]
    await api.mundo.como(UserRole.ADMIN)
    casos = [
        ("UPDATE recaudos SET valor_recibido = 1 WHERE id = :id", 409, "no se pueden modificar"),
        ("DELETE FROM recaudos WHERE id = :id", 403, "Su rol no permite esta operación"),
    ]
    for sql, codigo, mensaje in casos:
        with pytest.raises(DBAPIError) as info:
            async with api.mundo.db.begin_nested():
                await api.mundo.db.execute(text(sql), {"id": rid})
        traducido = traducir_error_db(info.value)
        assert traducido is not None
        assert traducido[0] == codigo
        assert mensaje in traducido[1]
        assert "<class" not in traducido[1]


async def test_descarga_de_reportes_por_http(api: Cliente) -> None:
    await api.post("AUXILIAR", "", parqueadero(await api.concepto("PARQUEADERO")))
    r = await api.get("ADMIN", "/reportes/general")
    assert r.status_code == 200
    assert r.json()["resumen"][0] == {"etiqueta": "Total recaudado", "valor": "$4.000"}

    xlsx = await api.get("ADMIN", "/reportes/parqueadero", formato="xlsx")
    assert xlsx.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert xlsx.headers["content-disposition"].startswith('attachment; filename="parqueadero-')
    assert xlsx.content[:2] == b"PK"  # un .xlsx es un ZIP
    pdf = await api.get("CONTABILIDAD", "/reportes/auditoria", formato="pdf")
    assert (pdf.headers["content-type"], pdf.content[:4]) == ("application/pdf", b"%PDF")

    assert (await api.get("AUXILIAR", "/reportes/caja")).status_code == 200
    assert (await api.get("AUXILIAR", "/reportes/general")).status_code == 403
    assert (await api.get("CONSEJO", "/reportes/general")).status_code == 403
    assert (await api.get("ADMIN", "/reportes/inventado")).status_code == 422
    assert (await api.get("CONSEJO", "/cortes")).json() == []
