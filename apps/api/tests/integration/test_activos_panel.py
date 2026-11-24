"""Fase 5 del módulo de activos: panel (también para el Consejo), proyección y reportes."""

from decimal import Decimal
from typing import Any

import pytest

from tests.integration.test_activos_api import HOY, Cliente, api, nuevo_activo, plan_aprobado  # noqa: F401

pytestmark = pytest.mark.integration


async def registrar(
    cliente: Cliente, activo: dict[str, Any], actividad_id: str | None, tipo: str = "PREVENTIVO", costo: str = "100000"
) -> dict[str, Any]:
    r = await cliente.post(
        "ADMIN",
        "/mantenimientos",
        {
            "activo_id": activo["id"],
            "actividad_id": actividad_id,
            "tipo": tipo,
            "fecha_ejecucion": str(HOY),
            "nombre_tecnico": "Pedro Ramírez",
            "actividades_realizadas": "Trabajo de prueba del panel",
            "estado_post_intervencion": "OPERATIVO",
            "costo_mano_obra": costo,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_panel_por_rol_y_consejo_solo_consolidados(api: Cliente) -> None:  # noqa: F811
    a = await nuevo_activo(api)
    await plan_aprobado(api, a["id"], costo_estimado="50000")
    [hoy] = (await api.get("ADMIN", "/actividades", desde=str(HOY), hasta=str(HOY))).json()
    await registrar(api, a, hoy["id"], costo="120000")
    await registrar(api, a, None, tipo="CORRECTIVO", costo="80000")

    admin = (await api.get("ADMIN", "/dashboard")).json()
    assert admin["activos"]["total"] == 1
    assert Decimal(str(admin["costos"]["mes"])) == Decimal(200000)
    assert Decimal(str(admin["costos"]["anio_correctivo"])) == Decimal(80000)
    assert admin["cumplimiento"]["mes"] == {"programadas": 1, "ejecutadas": 1, "a_tiempo": 1}
    assert admin["mantenimientos_mes"] == {"PREVENTIVO": 1, "CORRECTIVO": 1}
    assert Decimal(str(admin["proyeccion"]["plan"])) == Decimal(50000 * 12)  # mensual, personal interno
    assert admin["detalle"] is not None and admin["puede_ver_costos"] is True

    consejo = (await api.get("CONSEJO", "/dashboard")).json()  # RLS le niega el detalle, pero ve los consolidados
    assert consejo["detalle"] is None
    assert consejo["costos"] == admin["costos"] and consejo["proyeccion"] == admin["proyeccion"]

    auxiliar = (await api.get("AUXILIAR", "/dashboard")).json()
    assert auxiliar["costos"] is None and auxiliar["proyeccion"] is None
    assert "costo_pendiente" not in auxiliar["recomendaciones"]
    assert auxiliar["semaforo"] == admin["semaforo"]
    assert (await api.get("CONSEJO", "")).status_code == 403  # el listado de activos sigue cerrado para el Consejo


async def test_contrato_anual_no_se_suma_dos_veces(api: Cliente) -> None:  # noqa: F811
    r = await api.post(
        "ADMIN",
        "/contratistas",
        {
            "razon_social": "Ascensores Prueba S.A.S.",
            "valor_contrato": "12000000",
            "vigencia_contrato_fin": str(HOY.replace(year=HOY.year + 1)),
        },
    )
    contratista = r.json()["id"]
    a = await nuevo_activo(api, mantenedor_id=contratista)
    await plan_aprobado(api, a["id"], costo_estimado="900000", contratista_id=contratista)
    proy = (await api.get("ADMIN", "/dashboard")).json()["proyeccion"]
    assert Decimal(str(proy["plan"])) == 0  # el plan lo cubre el contrato
    assert Decimal(str(proy["contratos"])) == Decimal(12000000)

    # Filtrar por una categoría sin activos de ese contratista deja fuera su contrato
    otra = next(c for c in (await api.get("ADMIN", "/categorias")).json() if c["codigo"] == "INFRAESTRUCTURA")
    assert (
        Decimal(str((await api.get("ADMIN", "/dashboard", categoria_id=otra["id"])).json()["proyeccion"]["contratos"]))
        == 0
    )


async def test_reportes_en_tres_formatos_y_permisos(api: Cliente) -> None:  # noqa: F811
    a = await nuevo_activo(api)
    await plan_aprobado(api, a["id"], costo_estimado="75000")
    await api.post(
        "ADMIN",
        "/recomendaciones",
        {
            "activo_id": a["id"],
            "descripcion": "Cambiar el tablero de control",
            "prioridad": "MEDIA",
            "costo_estimado": "1000000",
        },
    )
    for tipo in ("inventario", "cumplimiento", "correctivos", "recomendaciones", "costos", "infraestructura"):
        r = await api.get("ADMIN", f"/reportes/{tipo}")
        assert r.status_code == 200, (tipo, r.text)
        assert r.json()["tablas"], tipo
    pdf = await api.get("ADMIN", "/reportes/inventario", formato="pdf")
    xlsx = await api.get("ADMIN", "/reportes/costos", formato="xlsx")
    assert pdf.content[:4] == b"%PDF" and xlsx.content[:2] == b"PK"
    assert "inventario-" in pdf.headers["content-disposition"]

    # La proyección del informe, partida por partida, cuadra con la del panel (misma regla en SQL y Python)
    costos = (await api.get("ADMIN", "/reportes/costos")).json()
    panel = (await api.get("ADMIN", "/dashboard")).json()["proyeccion"]
    tabla_plan = next(t for t in costos["tablas"] if t["titulo"].endswith("plan preventivo"))
    tabla_recs = next(t for t in costos["tablas"] if t["titulo"].endswith("recomendaciones pendientes"))
    assert Decimal(str(tabla_plan["totales"][-1])) == Decimal(str(panel["plan"])) == Decimal(75000 * 12)
    assert (
        Decimal(str(tabla_recs["totales"][-1])) == Decimal(str(panel["recomendaciones"])) == Decimal(600000)
    )  # media: 60 %

    assert (await api.get("AUXILIAR", "/reportes/costos")).status_code == 403
    assert (await api.get("MANTENIMIENTO", "/reportes/cumplimiento")).status_code == 403
    aux = (await api.get("AUXILIAR", "/reportes/recomendaciones")).json()
    assert "Costo estimado" not in [c["titulo"] for c in aux["tablas"][0]["columnas"]]  # sin costos para recepción
    assert (await api.get("ADMIN", "/reportes/costos", desde="2026-01-01", hasta="2025-01-01")).status_code == 400


async def test_dossier_con_qr_y_sin_costos_para_el_tecnico(api: Cliente) -> None:  # noqa: F811
    import pymupdf

    a = await nuevo_activo(api, especificaciones={"Potencia": "15 HP"})
    await plan_aprobado(api, a["id"])
    r = await api.get("MANTENIMIENTO", f"/{a['id']}/dossier.pdf")
    assert r.status_code == 200 and r.headers["content-disposition"].endswith('hoja-de-vida-ACT-001.pdf"')
    doc = pymupdf.open("pdf", r.content)
    texto = doc[0].get_text()
    assert "Hoja de vida · ACT-001" in texto and "Potencia" in texto
    assert "Costo acumulado" not in texto  # el técnico no ve costos
    assert len(doc[0].get_images()) == 1  # el QR
    admin = pymupdf.open("pdf", (await api.get("ADMIN", f"/{a['id']}/dossier.pdf")).content)
    assert "Costo acumulado" in admin[0].get_text()
    assert (await api.get("ADMIN", f"/{a['id']}/dossier.xlsx")).content[:2] == b"PK"
