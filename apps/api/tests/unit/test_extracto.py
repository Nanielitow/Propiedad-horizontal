"""Lectura de extractos bancarios y sugerencia de la unidad que pagó (sin base de datos)."""

import io
import uuid
from datetime import date
from decimal import Decimal

import pytest
from openpyxl import Workbook

from app.services.cartera import extracto as ex
from app.services.comun import ValidacionError


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("1.234.567,89", "1234567.89"),
        ("1,234,567.89", "1234567.89"),
        ("$ 450.000", "450000"),
        ("450,000", "450000"),
        ("929500", "929500"),
        ("(12.000)", "-12000"),
        ("-15000,50", "-15000.50"),
        ("", None),
        ("abc", None),
    ],
)
def test_montos_de_banco(texto: str, esperado: str | None) -> None:
    v = ex.parse_monto(texto)
    assert (v is None and esperado is None) or v == Decimal(esperado)  # type: ignore[arg-type]


def test_fechas_de_banco() -> None:
    for t in ("2026/11/24", "24/11/2026", "2026-11-24", "24-11-2026", "20261124"):
        assert ex.parse_fecha(t) == date(2026, 11, 24), t


def test_csv_tipo_bancolombia_con_valor_con_signo() -> None:
    csv = (
        "Banco X - Movimientos de la cuenta 123\nPeriodo: noviembre\n\n"
        "FECHA;DESCRIPCIÓN;SUCURSAL;DCTO.;VALOR;SALDO\n"
        "2026/11/02;TRANSFERENCIA APTO 502 T1;0001;;929.500,00;10.000.000,00\n"
        "2026/11/03;PAGO SERVICIO ENERGIA;0001;;-1.200.000,00;8.800.000,00\n"
        "2026/11/05;CONSIGNACION EFECTIVO;0123;778899;777.300,00;9.577.300,00\n"
    ).encode("latin-1")
    movs = ex.leer_extracto(csv, "movimientos.csv")
    assert [(m.fecha, m.valor) for m in movs] == [
        (date(2026, 11, 2), Decimal("929500.00")),
        (date(2026, 11, 5), Decimal("777300.00")),
    ]
    assert movs[1].referencia == "778899" and ex.medio_de(movs[1]).value == "CONSIGNACION"


def test_excel_con_columnas_de_credito_y_debito() -> None:
    wb = Workbook()
    hoja = wb.active
    hoja.append(["Fecha", "Descripción", "Referencia", "Nombre del ordenante", "Débito", "Crédito"])
    hoja.append([date(2026, 11, 10), "ABONO TRANSFERENCIA", "TRF123456", "CLAUDIA TORRES JIMENEZ", None, 929500])
    hoja.append([date(2026, 11, 11), "COMISION", None, None, 15000, None])
    buf = io.BytesIO()
    wb.save(buf)
    movs = ex.leer_extracto(buf.getvalue(), "extracto.xlsx")
    assert len(movs) == 1 and movs[0].pagador == "CLAUDIA TORRES JIMENEZ" and movs[0].referencia == "TRF123456"


def test_extracto_sin_columnas_reconocibles() -> None:
    with pytest.raises(ValidacionError, match="No encontré las columnas"):
        ex.leer_extracto(b"a;b;c\n1;2;3\n", "raro.csv")
    with pytest.raises(ValidacionError, match=".xls antiguo"):
        ex.leer_extracto(b"\xd0\xcf\x11\xe0basura", "viejo.xls")


def test_referencia_estable_sin_referencia_del_banco() -> None:
    m = ex.MovimientoBanco(1, date(2026, 11, 2), "TRANSFERENCIA  apto 502", None, None, Decimal("929500.00"))
    otra = ex.MovimientoBanco(9, date(2026, 11, 2), "transferencia apto 502", None, None, Decimal("929500.00"))
    assert ex.referencia_estable(m) == ex.referencia_estable(otra)  # mismo movimiento al volver a subir el archivo
    assert ex.referencia_estable(m).startswith("EXT-20261102-929500-")
    con_ref = ex.MovimientoBanco(1, date(2026, 11, 2), "x", "TRF123456", None, Decimal("1"))
    assert ex.referencia_estable(con_ref) == "TRF123456"


def _u(
    etiqueta: str,
    torre: str,
    numero: str,
    montos: frozenset[str] = frozenset(),
    nombres: tuple[tuple[str, bool], ...] = (),
) -> ex.UnidadCandidata:
    return ex.UnidadCandidata(
        uuid.uuid4(), etiqueta, torre, numero, {Decimal(m) for m in montos}, [(ex._palabras(n), r) for n, r in nombres]
    )


UNIDADES = [
    _u("1-502", "1", "502", frozenset({"929500.00"}), (("Carlos Pérez Gómez", True),)),
    _u("2-502", "2", "502", frozenset({"777300.00"}), (("Ana Ruiz", True),)),
    _u("1-101", "1", "101", frozenset({"777300.00"}), (("Claudia Torres Jiménez", True),)),
    _u("L-01", "", "L-01", frozenset({"561400.00"}), (("Gustavo Ramírez López", True),)),
]


def _mov(desc: str, valor: str, pagador: str | None = None) -> ex.MovimientoBanco:
    return ex.MovimientoBanco(1, date(2026, 11, 2), desc, None, pagador, Decimal(valor))


def test_unidad_en_la_referencia_y_valor_unico() -> None:
    u, puntos, motivos = ex.puntuar(_mov("TRANSFERENCIA T1 APTO 502", "929500.00"), UNIDADES)
    assert u is not None and u.etiqueta == "1-502" and ex.confianza(puntos) == "alta" and len(motivos) == 2


def test_numero_repetido_en_dos_torres_necesita_la_torre() -> None:
    # «APTO 502» sin torre es ambiguo (existe en las dos): no se sugiere por el número
    u, puntos, _ = ex.puntuar(_mov("PAGO APTO 502", "100000.00"), UNIDADES)
    assert ex.confianza(puntos) == "ninguna"
    u, _, _ = ex.puntuar(_mov("PAGO TORRE 2 APTO 502", "100000.00"), UNIDADES)
    assert u is not None and u.etiqueta == "2-502"


def test_por_nombre_del_pagador() -> None:
    u, puntos, motivos = ex.puntuar(_mov("ABONO TRANSFERENCIA", "50000.00", "CLAUDIA TORRES JIMENEZ"), UNIDADES)
    assert u is not None and u.etiqueta == "1-101" and ex.confianza(puntos) == "media"
    assert any("responsable de pago" in m for m in motivos)


def test_valor_que_deben_varias_unidades_no_basta() -> None:
    u, puntos, _ = ex.puntuar(_mov("ABONO", "777300.00"), UNIDADES)
    assert ex.confianza(puntos) == "ninguna"  # 2-502 y 1-101 deben lo mismo


def test_local_con_letras() -> None:
    u, _, _ = ex.puntuar(_mov("PAGO LOCAL L-01", "561400.00"), UNIDADES)
    assert u is not None and u.etiqueta == "L-01"
