"""API de cartera por HTTP: configuración, facturación, pagos, estado de cuenta, morosos,
paz y salvo, documentos PDF/Excel y permisos por rol."""

import io
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

import httpx
import pytest
from openpyxl import load_workbook
from redis.asyncio import Redis
from sqlalchemy import text

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.security import create_access_token
from app.db.rls import set_rls_context
from app.main import app
from app.services.comun import hoy_bogota
from tests.integration.conftest import Mundo

pytestmark = pytest.mark.integration
HOY = hoy_bogota()
MES_PASADO = (HOY.replace(day=1) - timedelta(days=1)).replace(day=1)


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

    async def put(self, quien: str, ruta: str, body: dict[str, Any]) -> httpx.Response:
        return await self.http.put(self.base + ruta, json=body, headers=self._auth(quien))


@pytest.fixture
async def api(mundo: Mundo, sin_limites: None) -> AsyncIterator[Cliente]:
    for rol in ("RESIDENTE", "CONSEJO"):
        await mundo.usuario(rol, rol)
    await set_rls_context(mundo.db, tenant_id=mundo.tenant, role="SYSTEM")
    await mundo.db.execute(text("SELECT seed_conceptos_cartera(:t)"), {"t": mundo.tenant})

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


async def _preparar(api: Cliente) -> dict[str, str]:
    """Unidades 101 (60 %, de la residente) y 102 (40 %), configuración y el periodo del mes pasado."""
    u = {}
    for numero, coef in (("101", "60"), ("102", "40")):
        r = await api.post("ADMIN", "/unidades", {"tower": "1", "number": numero, "coefficient": coef})
        u[numero] = r.json()["id"]
    r = await api.post(
        "ADMIN",
        f"/unidades/{u['101']}/vinculos",
        {
            "relacion": "PROPIETARIO",
            "persona": {"nombre_completo": "Ana Propietaria", "user_id": str(api.mundo.usuarios["RESIDENTE"])},
        },
    )
    assert r.status_code == 201, r.text
    r = await api.put(
        "ADMIN", "/cartera/config", {"metodo": "COEFICIENTE", "presupuesto_mensual": "1000000", "dia_vencimiento": 10}
    )
    assert r.status_code == 200, r.text
    r = await api.post(
        "ADMIN",
        "/cartera/periodos",
        {"anio": MES_PASADO.year, "mes": MES_PASADO.month, "fecha_emision": MES_PASADO.isoformat()},
    )
    assert r.status_code == 201, r.text
    return u


async def test_facturar_y_cobrar(api: Cliente) -> None:
    u = await _preparar(api)
    previa = (await api.post("ADMIN", "/cartera/periodos/previa", {"anio": HOY.year, "mes": HOY.month})).json()
    assert previa["total_cuotas"] == "1000000.00" and previa["total_intereses"] == "15000.00"  # 1,5 % de lo vencido
    r = await api.post("ADMIN", "/cartera/periodos", {"anio": HOY.year, "mes": HOY.month})
    assert r.status_code == 201 and r.json()["nombre"].startswith(
        (
            "Enero",
            "Febrero",
            "Marzo",
            "Abril",
            "Mayo",
            "Junio",
            "Julio",
            "Agosto",
            "Septiembre",
            "Octubre",
            "Noviembre",
            "Diciembre",
        )
    )
    r = await api.post("ADMIN", "/cartera/periodos", {"anio": HOY.year, "mes": HOY.month})
    assert r.status_code == 400 and "ya fue emitido" in r.json()["detail"]

    pago = await api.post(
        "CONTABILIDAD",
        "/cartera/pagos",
        {
            "unidad_id": u["101"],
            "fecha_pago": HOY.isoformat(),
            "valor": "700000",
            "medio_pago": "TRANSFERENCIA",
            "referencia": "abc-1",
        },
    )
    assert pago.status_code == 201, pago.text
    p = pago.json()
    assert [a["descripcion"].split()[0] for a in p["aplicaciones"]] == ["Intereses", "Cuota", "Cuota"]
    assert p["saldo_pendiente"] == "509000.00" and p["pago"]["referencia"] == "ABC-1"

    recibo = await api.get("ADMIN", f"/cartera/pagos/{p['pago']['id']}/recibo.pdf")
    assert recibo.status_code == 200 and recibo.content.startswith(b"%PDF")

    ec = (await api.get("ADMIN", f"/cartera/unidades/{u['101']}/estado-cuenta")).json()
    assert ec["saldo_total"] == "509000.00" and ec["responsable"] == "Ana Propietaria"
    assert ec["movimientos"][-1]["saldo"] == "509000.00"
    pdf = await api.get("ADMIN", f"/cartera/unidades/{u['101']}/estado-cuenta", formato="pdf")
    assert pdf.content.startswith(b"%PDF")

    morosos = (await api.get("AUXILIAR", "/cartera/morosos")).json()
    assert [m["unidad"] for m in morosos["items"]] == ["1-102"]  # el 101 abonó lo vencido
    xlsx = await api.get("ADMIN", "/cartera/morosos", formato="xlsx")
    assert "Unidades en mora" in load_workbook(io.BytesIO(xlsx.content)).sheetnames

    resumen = (await api.get("CONSEJO", "/cartera/resumen")).json()
    assert resumen["unidades_en_mora"] == 1 and resumen["recaudo_pct"] is not None
    assert len(resumen["recaudo_mensual"]) == 12


async def test_paz_y_salvo(api: Cliente) -> None:
    u = await _preparar(api)
    r = await api.post("RESIDENTE", f"/cartera/unidades/{u['101']}/paz-y-salvo")
    assert r.status_code == 400 and "saldo vencido" in r.json()["detail"]
    await api.post(
        "ADMIN",
        "/cartera/pagos",
        {"unidad_id": u["101"], "fecha_pago": HOY.isoformat(), "valor": "600000", "medio_pago": "EFECTIVO"},
    )
    r = await api.post("RESIDENTE", f"/cartera/unidades/{u['101']}/paz-y-salvo")
    assert r.status_code == 201, r.text
    p = r.json()
    pdf = await api.get("RESIDENTE", f"/cartera/paz-y-salvo/{p['id']}.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    v = (await api.get("ADMIN", f"/cartera/paz-y-salvo/verificar/{p['codigo_verificacion']}")).json()
    assert v["valido"] and v["unidad"] == "1-101"
    # La residente no puede pedir el de una unidad ajena
    assert (await api.post("RESIDENTE", f"/cartera/unidades/{u['102']}/paz-y-salvo")).status_code == 404


async def test_residente_y_permisos(api: Cliente) -> None:
    u = await _preparar(api)
    mia = (await api.get("RESIDENTE", "/cartera/mi-cartera")).json()
    assert [e["unidad"] for e in mia] == ["1-101"] and mia[0]["saldo_vencido"] == "600000.00"
    assert (await api.get("RESIDENTE", f"/cartera/unidades/{u['102']}/estado-cuenta")).status_code == 404
    assert (await api.get("RESIDENTE", "/cartera/morosos")).status_code == 403
    pago = {"unidad_id": u["102"], "fecha_pago": HOY.isoformat(), "valor": "1000", "medio_pago": "EFECTIVO"}
    assert (await api.post("CONSEJO", "/cartera/pagos", pago)).status_code == 403
    assert (await api.post("AUXILIAR", "/cartera/periodos", {"anio": HOY.year, "mes": HOY.month})).status_code == 403
    r = await api.post("ADMIN", "/cartera/pagos", {**pago, "medio_pago": "TRANSFERENCIA"})
    assert r.status_code == 422  # transferencia sin referencia ni soporte
    r = await api.put("ADMIN", "/cartera/config", {"metodo": "COEFICIENTE"})
    assert r.status_code == 422  # falta el presupuesto
