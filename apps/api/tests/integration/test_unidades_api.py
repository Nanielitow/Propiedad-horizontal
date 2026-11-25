"""API del censo por HTTP: rutas, permisos por rol, datos ocultos, importación y exportación."""

import io
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from openpyxl import Workbook, load_workbook
from redis.asyncio import Redis

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.security import create_access_token
from app.db.rls import set_rls_context
from app.main import app
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

    async def get(self, quien: str, ruta: str, **params: Any) -> httpx.Response:
        return await self.http.get(self.base + ruta, params=params, headers=self._auth(quien))

    async def post(self, quien: str, ruta: str, body: dict[str, Any] | None = None) -> httpx.Response:
        return await self.http.post(self.base + ruta, json=body or {}, headers=self._auth(quien))

    async def patch(self, quien: str, ruta: str, body: dict[str, Any]) -> httpx.Response:
        return await self.http.patch(self.base + ruta, json=body, headers=self._auth(quien))

    async def subir(self, quien: str, ruta: str, contenido: bytes, **form: str) -> httpx.Response:
        archivos = {"archivo": ("censo.xlsx", contenido, "application/octet-stream")}
        return await self.http.post(self.base + ruta, files=archivos, data=form, headers=self._auth(quien))


@pytest.fixture
async def api(mundo: Mundo, sin_limites: None) -> AsyncIterator[Cliente]:
    for rol in ("RESIDENTE", "CONSEJO", "MANTENIMIENTO"):
        await mundo.usuario(rol, rol)
    await set_rls_context(mundo.db, tenant_id=mundo.tenant, role="SYSTEM")

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


async def _censo_basico(api: Cliente) -> dict[str, Any]:
    """Unidad 1-101 con parqueadero anexo, propietaria con cuenta (el residente) y un vehículo."""
    apto = (await api.post("ADMIN", "/unidades", {"tower": "Torre 1", "number": "101", "coefficient": "60"})).json()
    r = await api.post(
        "ADMIN",
        "/unidades",
        {"tower": "1", "number": "PQ-01", "tipo": "PARQUEADERO", "unidad_principal_id": apto["id"]},
    )
    assert r.status_code == 201, r.text
    await api.post("ADMIN", "/unidades", {"tower": "1", "number": "102", "coefficient": "40"})
    r = await api.post(
        "ADMIN",
        f"/unidades/{apto['id']}/vinculos",
        {
            "relacion": "PROPIETARIO",
            "reside": True,
            "persona": {
                "nombre_completo": "carolina ruiz",
                "tipo_documento": "CC",
                "numero_documento": "52.111.222",
                "telefono": "300 111 2222",
                "email": "Caro@Correo.com",
                "user_id": str(api.mundo.usuarios["RESIDENTE"]),
                "autoriza_datos": True,
            },
        },
    )
    assert r.status_code == 201, r.text
    r = await api.post("ADMIN", f"/unidades/{apto['id']}/vehiculos", {"placa": "xyz-987", "marca": "Kia"})
    assert r.status_code == 201, r.text
    return r.json()


async def test_flujo_de_administracion(api: Cliente) -> None:
    ficha = await _censo_basico(api)
    assert ficha["etiqueta"] == "1-101"
    assert ficha["ocupacion"] == "PROPIETARIO"  # se calculó al vincular a la propietaria que reside
    assert [a["etiqueta"] for a in ficha["anexos"]] == ["1-PQ-01"]
    v = ficha["vinculos"][0]
    assert v["persona"]["nombre_completo"] == "Carolina Ruiz"
    assert v["persona"]["numero_documento"] == "52111222" and v["persona"]["email"] == "caro@correo.com"
    assert v["responsable_pago"] and v["es_contacto_principal"]
    assert [x["placa"] for x in ficha["vehiculos_lista"]] == ["XYZ987"]
    assert any(a["entidad"] == "vinculo" for a in ficha["auditoria"])

    resumen = (await api.get("ADMIN", "/unidades/resumen")).json()
    assert resumen["total"] == 3 and resumen["por_tipo"] == {"APARTAMENTO": 2, "PARQUEADERO": 1}
    assert resumen["coeficientes"]["cuadra"]  # el anexo sin coeficiente no cuenta como faltante
    assert resumen["sin_propietario"] == 1 and resumen["torres"] == ["1"]

    lista = (await api.get("ADMIN", "/unidades", texto="carolina")).json()
    assert [u["etiqueta"] for u in lista["items"]] == ["1-101"]
    assert (await api.get("ADMIN", "/unidades", texto="XYZ-987")).json()["total"] == 1
    assert (await api.get("ADMIN", "/unidades", sin_propietario=True)).json()["items"][0]["etiqueta"] == "1-102"

    r = await api.post("ADMIN", f"/vinculos/{v['id']}/cerrar", {"motivo": "Venta del apartamento"})
    assert r.status_code == 200
    assert r.json()["vinculos"] == [] and r.json()["historial"][0]["motivo_cierre"] == "Venta del apartamento"
    assert r.json()["ocupacion"] == "SIN_INFORMACION"


async def test_errores_de_negocio_son_400(api: Cliente) -> None:
    await api.post("ADMIN", "/unidades", {"tower": "1", "number": "101"})
    r = await api.post("ADMIN", "/unidades", {"tower": "T1", "number": "101"})
    assert r.status_code == 400 and "Ya existe la unidad 1-101" in r.json()["detail"]
    r = await api.post("AUXILIAR", "/unidades", {"number": "999"})
    assert r.status_code == 403
    r = await api.get("ADMIN", "/vehiculos/placa/%23%23")
    assert r.status_code == 400


async def test_cada_rol_ve_lo_suyo(api: Cliente) -> None:
    ficha = await _censo_basico(api)
    apto = ficha["id"]

    # Recepción: directorio y teléfono, sin documento, correo ni coeficientes
    aux = (await api.get("AUXILIAR", f"/unidades/{apto}")).json()
    p = aux["vinculos"][0]["persona"]
    assert p["telefono"] == "3001112222" and p["numero_documento"] is None and p["email"] is None
    assert aux["coefficient"] is None and aux["auditoria"] == []
    placa = (await api.get("AUXILIAR", "/vehiculos/placa/xyz987")).json()
    assert placa["registrada"] and placa["vehiculo"]["unidad"]["etiqueta"] == "1-101"
    assert (await api.get("AUXILIAR", "/vehiculos/placa/AAA000")).json()["registrada"] is False

    # Consejo: unidades y coeficientes, sin directorio
    consejo = (await api.get("CONSEJO", "/unidades")).json()
    assert consejo["items"][0]["coefficient"] == "60.0000" and consejo["items"][0]["propietarios"] == []
    assert (await api.get("CONSEJO", "/personas")).status_code == 403

    # Mantenimiento: unidades sin coeficientes; no ve vehículos
    mant = (await api.get("MANTENIMIENTO", "/unidades")).json()
    assert mant["total"] == 3 and mant["items"][0]["coefficient"] is None and mant["items"][0]["vehiculos"] is None

    # Residente: no lista el censo; ve "mi unidad" con sus propios datos completos
    assert (await api.get("RESIDENTE", "/unidades")).status_code == 403
    mias = (await api.get("RESIDENTE", "/mi-unidad")).json()
    assert [u["etiqueta"] for u in mias] == ["1-101"]
    assert mias[0]["coefficient"] == "60.0000"
    assert mias[0]["vinculos"][0]["persona"]["numero_documento"] == "52111222"  # es ella
    assert [v["placa"] for v in mias[0]["vehiculos_lista"]] == ["XYZ987"]
    otra = (await api.get("ADMIN", "/unidades", texto="102")).json()["items"][0]["id"]
    assert (await api.get("RESIDENTE", f"/unidades/{otra}")).status_code == 404


async def test_directorio(api: Cliente) -> None:
    await _censo_basico(api)
    r = (await api.get("ADMIN", "/personas", texto="RUIZ")).json()
    assert r["total"] == 1 and r["items"][0]["unidades"][0]["etiqueta"] == "1-101"
    assert r["items"][0]["relaciones"] == ["PROPIETARIO"]
    assert (await api.get("ADMIN", "/personas", texto="52111222")).json()["total"] == 1
    # Recepción no busca por documento (no lo puede ver)
    assert (await api.get("AUXILIAR", "/personas", texto="52111222")).json()["total"] == 0
    persona = r["items"][0]["id"]
    r = await api.patch("ADMIN", f"/personas/{persona}", {"telefono": "3109998888"})
    assert r.status_code == 200 and r.json()["telefono"] == "3109998888"


async def test_exportar_censo(api: Cliente) -> None:
    await _censo_basico(api)
    r = await api.get("ADMIN", "/unidades/exportar", formato="xlsx")
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    assert {"Resumen", "Unidades", "Personas", "Vehículos"} <= set(wb.sheetnames)
    r = await api.get("CONSEJO", "/unidades/exportar", formato="xlsx")
    assert "Personas" not in load_workbook(io.BytesIO(r.content)).sheetnames  # sin datos de contacto
    r = await api.get("ADMIN", "/unidades/exportar", formato="pdf")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert (await api.get("AUXILIAR", "/unidades/exportar")).status_code == 403


# --- Importación ----------------------------------------------------------------------


def _excel(
    unidades: list[list[Any]], personas: list[list[Any]] | None = None, vehiculos: list[list[Any]] | None = None
) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Unidades"
    ws.append(["Torre", "Apto", "Tipo", "Coeficiente", "Área", "Anexo de"])  # encabezados "a mano"
    for f in unidades:
        ws.append(f)
    if personas is not None:
        wp = wb.create_sheet("Propietarios")
        wp.append(["Torre", "Número", "Relación", "Nombre", "Cédula", "Celular", "Correo", "Reside", "Paga"])
        for f in personas:
            wp.append(f)
    if vehiculos is not None:
        wv = wb.create_sheet("Vehículos")
        wv.append(["Torre", "Número", "Placa", "Tipo"])
        for f in vehiculos:
            wv.append(f)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def test_plantilla(api: Cliente) -> None:
    r = await api.get("ADMIN", "/unidades/importar/plantilla")
    assert r.status_code == 200
    assert load_workbook(io.BytesIO(r.content)).sheetnames == ["Instrucciones", "Unidades", "Personas", "Vehículos"]
    # La plantilla tal cual (con sus filas de ejemplo) se puede importar
    previa = (await api.subir("ADMIN", "/unidades/importar/previa", r.content)).json()
    assert previa["errores"] == [] and previa["totales"]["unidades_nuevas"] == 2


async def test_importar_previa_confirmar_e_idempotencia(api: Cliente) -> None:
    contenido = _excel(
        [
            ["Torre 1", 101, "Apartamento", "50,5", 62.5, None],
            ["T1", 102.0, "apto", "49,5 %", 70, None],
            ["1", "PQ-1", "Garaje", None, 12, "1-101"],
        ],
        [
            ["1", "101", "Propietario", "PEDRO PÉREZ", "79.000.111", "300 222 3333", "pedro@correo.com", "Sí", "Sí"],
            ["1", "101", "Residente", "Lucía Pérez", None, None, None, "Sí", None],
            ["1", "102", "Arrendataria", "Marta Gil", "1010101010", None, None, "x", None],
            ["1", "102", "Propietario", "Pedro Pérez", "79000111", None, None, "No", None],
        ],
        [["1", "101", "abc 123", "Carro"]],
    )
    previa = (await api.subir("ADMIN", "/unidades/importar/previa", contenido)).json()
    assert previa["errores"] == [], previa["errores"]
    t = previa["totales"]
    assert (t["unidades_nuevas"], t["personas_nuevas"], t["vinculos_nuevos"], t["vehiculos_nuevos"]) == (3, 3, 4, 1)
    assert previa["coeficientes"]["cuadra"]
    assert any("se asumió CC" in a for a in previa["advertencias"])
    # Nada se guardó todavía
    assert (await api.get("ADMIN", "/unidades")).json()["total"] == 0

    r = await api.subir("ADMIN", "/unidades/importar/confirmar", contenido, sha256="0" * 64)
    assert r.status_code == 400 and "no coincide" in r.json()["detail"]
    r = await api.subir("ADMIN", "/unidades/importar/confirmar", contenido, sha256=previa["sha256"])
    assert r.status_code == 200, r.text
    assert r.json()["unidades_creadas"] == 3 and r.json()["personas_creadas"] == 3 and r.json()["vinculos_creados"] == 4

    lista = {u["etiqueta"]: u for u in (await api.get("ADMIN", "/unidades")).json()["items"]}
    assert lista["1-PQ-1"]["unidad_principal"]["etiqueta"] == "1-101"
    assert lista["1-102"]["ocupacion"] == "ARRENDADA"
    assert lista["1-102"]["responsable_pago"]["nombre"] == "Pedro Pérez"  # primer propietario, automático
    assert lista["1-101"]["vehiculos"] == 1

    # Reimportar el mismo archivo: no hay cambios
    previa2 = (await api.subir("ADMIN", "/unidades/importar/previa", contenido)).json()
    assert previa2["hay_cambios"] is False and previa2["puede_aplicar"] is False


async def test_importar_detecta_errores_por_fila(api: Cliente) -> None:
    contenido = _excel(
        [
            ["1", "101", "Apartamento", "0,5", None, None],
            ["1", "101", "Apartamento", "0,5", None, None],
            ["1", "103", "Castillo", "abc", None, None],
            ["1", "PQ-9", "Parqueadero", None, None, "9-999"],
        ],
        [["1", "555", "Propietario", "Nadie", None, None, None, None, None]],
        [["1", "101", "!!", None]],
    )
    previa = (await api.subir("ADMIN", "/unidades/importar/previa", contenido)).json()
    mensajes = {(e["hoja"], e["fila"]): e["mensaje"] for e in previa["errores"]}
    assert "repetida" in mensajes[("Unidades", 3)]
    assert "no reconocido" in mensajes[("Unidades", 4)]
    assert "9-999 no existe" in mensajes[("Unidades", 5)]
    assert "555 no existe" in mensajes[("Personas", 2)]
    assert "placa" in mensajes[("Vehículos", 2)].lower()
    assert previa["puede_aplicar"] is False
    r = await api.subir("ADMIN", "/unidades/importar/confirmar", contenido, sha256=previa["sha256"])
    assert r.status_code == 400 and "error" in r.json()["detail"]


async def test_importar_actualiza_y_exige_permiso(api: Cliente) -> None:
    await api.post("ADMIN", "/unidades", {"tower": "1", "number": "101", "coefficient": "100"})
    contenido = _excel([["1", "101", None, "100", 80, None]])  # solo agrega el área
    previa = (await api.subir("ADMIN", "/unidades/importar/previa", contenido)).json()
    assert previa["unidades_con_cambios"][0]["cambios"] == {"area_m2": {"antes": None, "despues": "80.00"}}
    r = await api.subir("ADMIN", "/unidades/importar/confirmar", contenido, sha256=previa["sha256"])
    assert r.json()["unidades_actualizadas"] == 1
    assert (await api.subir("AUXILIAR", "/unidades/importar/previa", contenido)).status_code == 403
    r = await api.http.post(
        api.base + "/unidades/importar/previa",
        files={"archivo": ("censo.csv", b"a,b", "text/csv")},
        headers=api._auth("ADMIN"),
    )
    assert r.status_code == 400 and ".xlsx" in r.json()["detail"]
