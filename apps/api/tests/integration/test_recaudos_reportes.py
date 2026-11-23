"""Fase 5: reportes (cifras, permisos, Excel y PDF) y cortes mensuales."""

import io
from datetime import date, timedelta
from decimal import Decimal

import pymupdf
import pytest
from openpyxl import load_workbook

from app.models.enums import MedioPago, UserRole
from app.schemas.recaudos import AplicacionIn, CierreCajaIn, ConsignacionCreate, RecaudoCreate
from app.services.recaudos import caja, conciliacion, cortes, exportar, reportes, service
from app.services.recaudos.dominio import TZ, ActorSimple, PermisoDenegado, ValidacionError
from tests.integration.conftest import AHORA, Mundo

pytestmark = pytest.mark.integration
HOY = AHORA.astimezone(TZ).date()  # fecha de Bogotá: en UTC puede ser ya el día siguiente
MES = (HOY.replace(day=1), reportes._fin_de_mes(HOY))


class AlmacenFalso:
    def __init__(self) -> None:
        self.archivos: dict[str, tuple[bytes, str]] = {}

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        self.archivos[key] = (data, content_type)

    def presign_get(self, key: str, filename: str, content_type: str = "application/pdf") -> str:
        return f"https://almacen.test/{key}?nombre={filename}"


async def registrar(
    m: Mundo, actor: ActorSimple, valor: int, medio: MedioPago = MedioPago.EFECTIVO, dias_atras: int = 0
):
    otros = await m.concepto("OTROS")
    return await service.registrar_recaudo(
        m.db,
        actor,
        RecaudoCreate(
            concepto_id=otros.id,
            medio_pago=medio,
            nombre_pagador="Visitante",
            valor_recibido=Decimal(valor),
            numero_comprobante=None if medio == MedioPago.EFECTIVO else "T-1",
            fecha_recaudo=AHORA - timedelta(days=dias_atras),
        ),
        ahora=AHORA,
    )


async def test_informe_general_suma_sin_anulados(mundo: Mundo) -> None:
    admin = await mundo.como(UserRole.ADMIN)
    await registrar(mundo, admin, 30000)
    await registrar(mundo, admin, 50000, MedioPago.TRANSFERENCIA)
    anulado = await registrar(mundo, admin, 99000)
    await service.anular_recaudo(mundo.db, admin, anulado.id, "Registro duplicado por error", ahora=AHORA)

    r = await reportes.generar_reporte(mundo.db, admin, "general", *MES)
    resumen = dict(r.resumen)
    assert resumen["Total recaudado"] == "$80.000"
    assert resumen["Anulados (no suman)"] == "1 por $99.000"
    por_medio = {fila[0]: fila[2] for fila in r.tablas[1].filas}
    assert por_medio == {"Efectivo": Decimal(30000), "Transferencia": Decimal(50000)}
    assert r.tablas[0].totales == ["Total", 2, Decimal(80000), Decimal(100)]


async def test_arqueo_cuadra_saldos_con_consignaciones(mundo: Mundo) -> None:
    admin = await mundo.como(UserRole.ADMIN)
    viejo = await registrar(mundo, admin, 40000, dias_atras=40)  # efectivo de un periodo anterior, aún en custodia
    nuevo = await registrar(mundo, admin, 25000)
    await caja.cerrar_caja(mundo.db, admin, CierreCajaIn(valor_fisico_contado=Decimal(65000)), ahora=AHORA)
    await conciliacion.registrar_consignacion(
        mundo.db,
        admin,
        ConsignacionCreate(
            fecha_consignacion=HOY,
            banco_destino="Bancolombia",
            referencia_bancaria="ARQ-1",
            valor_consignado=Decimal(50000),
            aplicaciones=[
                AplicacionIn(recaudo_id=viejo.id),
                AplicacionIn(recaudo_id=nuevo.id, valor_aplicado=Decimal(10000)),
            ],
        ),
        ahora=AHORA,
    )
    r = await reportes.generar_reporte(mundo.db, admin, "caja", *MES)
    movimiento = r.tablas[0]
    inicial, ingresos, consignado = (fila[1] for fila in movimiento.filas)
    final = movimiento.totales[1]
    assert (inicial, ingresos, consignado, final) == (Decimal(40000), Decimal(25000), Decimal(50000), Decimal(15000))
    assert inicial + ingresos - consignado == final
    assert len(r.tablas[1].filas) == 1  # el cierre del periodo


async def test_permisos_de_reportes(mundo: Mundo) -> None:
    auxiliar = await mundo.como(UserRole.AUXILIAR)
    await registrar(mundo, auxiliar, 12000)
    r = await reportes.generar_reporte(mundo.db, auxiliar, "caja", *MES)
    assert r.titulo.endswith("solo su caja")
    with pytest.raises(PermisoDenegado):
        await reportes.generar_reporte(mundo.db, auxiliar, "general", *MES)

    # El efectivo de otro auxiliar no aparece en su arqueo (RLS)
    otro = await mundo.usuario("AUX2", "AUXILIAR")
    await registrar(mundo, await mundo.como(UserRole.AUXILIAR, "AUX2"), 70000)
    assert otro
    auxiliar = await mundo.como(UserRole.AUXILIAR)
    r = await reportes.generar_reporte(mundo.db, auxiliar, "caja", *MES)
    assert r.tablas[0].filas[1][1] == Decimal(12000)

    consejo = ActorSimple(mundo.tenant, mundo.usuarios["ADMIN"], UserRole.CONSEJO)
    with pytest.raises(PermisoDenegado):
        await reportes.generar_reporte(mundo.db, consejo, "auditoria", *MES)
    with pytest.raises(ValidacionError, match="anterior"):
        await reportes.generar_reporte(mundo.db, await mundo.como(UserRole.ADMIN), "general", MES[1], MES[0])


async def test_excel_y_pdf_son_validos(mundo: Mundo) -> None:
    admin = await mundo.como(UserRole.ADMIN)
    await registrar(mundo, admin, 1234567)
    r = await reportes.generar_reporte(mundo.db, admin, "general", *MES)

    wb = load_workbook(io.BytesIO(exportar.a_excel(r)))
    assert wb.sheetnames == ["Resumen", "Por concepto", "Por medio de pago", "Por estado del dinero"]
    hoja = wb["Por concepto"]
    assert hoja["A4"].value == "Concepto"
    total = hoja["C5"]
    assert total.value == 1234567.0  # número, no texto: se puede sumar en Excel
    assert total.number_format == exportar.FORMATO_DINERO
    assert hoja.freeze_panes == "A5"

    pdf = exportar.a_pdf(r)
    assert pdf.startswith(b"%PDF")
    doc = pymupdf.open("pdf", pdf)
    texto = doc[0].get_text()
    assert "Informe general de ingresos" in texto
    assert "$1.234.567" in texto
    assert f"Página 1 de {doc.page_count}" in texto


async def test_corte_mensual_es_una_foto_unica(mundo: Mundo) -> None:
    admin = await mundo.como(UserRole.ADMIN)
    anterior = HOY.replace(day=1) - timedelta(days=1)
    await registrar(mundo, admin, 45000, dias_atras=(HOY - anterior.replace(day=10)).days)
    almacen = AlmacenFalso()

    generado = await cortes.generar_corte_manual(mundo.db, admin, anterior.year, anterior.month, almacen=almacen)
    clave = f"tenants/{mundo.tenant}/recaudos/cortes/{anterior:%Y-%m}"
    assert set(almacen.archivos) == {f"{clave}.pdf", f"{clave}.xlsx"}
    assert almacen.archivos[f"{clave}.pdf"][0].startswith(b"%PDF")
    assert Decimal(generado.corte.resumen["total_mes"]) == Decimal(45000)

    with pytest.raises(ValidacionError, match="no se regeneran"):
        await cortes.generar_corte_manual(mundo.db, admin, anterior.year, anterior.month, almacen=almacen)
    with pytest.raises(ValidacionError, match="meses ya cerrados"):
        await cortes.generar_corte_manual(mundo.db, admin, HOY.year, HOY.month, almacen=almacen)
    with pytest.raises(PermisoDenegado):
        contabilidad = await mundo.como(UserRole.CONTABILIDAD)
        await cortes.generar_corte_manual(mundo.db, contabilidad, 2020, 1, almacen=almacen)

    # El consejo lee los cortes (no el detalle de recaudos)
    await mundo.usuario("CONSEJO", "CONSEJO")
    consejo = await mundo.como(UserRole.CONSEJO)
    [vista] = await cortes.listar_cortes(mundo.db, consejo, almacen=almacen)
    assert vista.periodo == date(anterior.year, anterior.month, 1)
    assert vista.pdf_url and vista.pdf_url.endswith(f"corte-recaudos-{anterior:%Y-%m}.pdf")
    with pytest.raises(PermisoDenegado):
        await cortes.listar_cortes(mundo.db, await mundo.como(UserRole.AUXILIAR), almacen=almacen)


def test_mes_anterior_cruza_el_anio() -> None:
    assert cortes.mes_anterior(date(2027, 1, 1)) == (2026, 12)
    assert cortes.mes_anterior(date(2026, 11, 1)) == (2026, 10)
