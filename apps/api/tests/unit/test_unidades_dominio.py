"""Reglas puras del módulo de unidades: normalización y coeficientes."""

from decimal import Decimal

import pytest

from app.models.enums import OcupacionUnidad, RelacionUnidad, TipoDocumentoIdentidad
from app.services.unidades import dominio as d

P, A, R_, AU = (
    RelacionUnidad.PROPIETARIO,
    RelacionUnidad.ARRENDATARIO,
    RelacionUnidad.RESIDENTE,
    RelacionUnidad.AUTORIZADO,
)


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("1.020.304.050", "1020304050"),
        (" 1020 304050 ", "1020304050"),
        ("900.123.456-7", "900123456-7"),
        ("ab123", "AB123"),
    ],
)
def test_normalizar_documento(entrada: str, esperado: str) -> None:
    assert d.normalizar_documento(entrada) == esperado


@pytest.mark.parametrize("malo", ["12", "123#456", "1" * 21])
def test_documento_invalido(malo: str) -> None:
    with pytest.raises(ValueError, match="documento"):
        d.normalizar_documento(malo)


def test_placas() -> None:
    assert d.normalizar_placa("abc-123") == "ABC123"
    assert d.normalizar_placa(" xyz 12d ") == "XYZ12D"
    assert d.normalizar_placa("b12") == "B12"
    with pytest.raises(ValueError):
        d.normalizar_placa("AB")


def test_telefono() -> None:
    assert d.normalizar_telefono("(+57) 300 123-4567") == "+573001234567"
    assert d.normalizar_telefono("601 234 5678") == "6012345678"
    with pytest.raises(ValueError):
        d.normalizar_telefono("12345")


def test_nombres() -> None:
    assert d.normalizar_nombre("  JUAN   CARLOS DE LA  TORRE ") == "Juan Carlos de la Torre"
    assert d.normalizar_nombre("maría del pilar") == "María del Pilar"
    assert d.normalizar_nombre("Ana McAllister") == "Ana McAllister"  # mezcla: se respeta
    with pytest.raises(ValueError):
        d.normalizar_nombre("   ")


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Torre 2", "2"),
        ("T2", "2"),
        ("t-3", "3"),
        ("Bloque A", "A"),
        ("Interior 4", "4"),
        (" ", ""),
        (None, ""),
        ("Sur", "SUR"),
        ("Bosque", "BOSQUE"),
        ("B-3", "3"),
    ],
)
def test_torre(entrada: str | None, esperado: str) -> None:
    assert d.normalizar_torre(entrada) == esperado


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [("Apto 301", "301"), ("301.0", "301"), (502, "502"), ("pq-05", "PQ-05"), ("Casa 12", "12")],
)
def test_numero(entrada: str | int, esperado: str) -> None:
    assert d.normalizar_numero(entrada) == esperado


def test_etiqueta() -> None:
    assert d.etiqueta("2", "301") == "2-301"
    assert d.etiqueta("", "12") == "12"


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("0,8532", Decimal("0.8532")),
        ("0.8532", Decimal("0.8532")),
        ("0,85 %", Decimal("0.85")),
        ("1.234,5", Decimal("1234.5")),
        ("1,234.5", Decimal("1234.5")),
        (0.8532, Decimal("0.8532")),
        (3, Decimal("3")),
    ],
)
def test_decimales_colombianos(entrada: str | float, esperado: Decimal) -> None:
    assert d.parsear_decimal(entrada) == esperado


def test_coeficiente() -> None:
    assert d.parsear_coeficiente("0,853217") == Decimal("0.8532")
    for malo in ("0", "-1", "100,5", "abc"):
        with pytest.raises(ValueError):
            d.parsear_coeficiente(malo)


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("C.C.", "CC"),
        ("cédula", "CC"),
        ("Cédula de ciudadanía", "CC"),
        ("ce", "CE"),
        ("PEP", "PPT"),
        ("Pasaporte", "PASAPORTE"),
    ],
)
def test_tipo_documento(entrada: str, esperado: str) -> None:
    assert d.parsear_tipo_documento(entrada) == TipoDocumentoIdentidad(esperado)


def test_tipo_documento_desconocido() -> None:
    with pytest.raises(ValueError, match="no reconocido"):
        d.parsear_tipo_documento("RUT")


def test_estado_coeficientes() -> None:
    ok = d.estado_coeficientes([Decimal("33.3333"), Decimal("33.3333"), Decimal("33.3334")])
    assert ok.cuadra and ok.diferencia == 0
    casi = d.estado_coeficientes([Decimal("50"), Decimal("49.995")])
    assert casi.cuadra  # dentro de la tolerancia de redondeo
    falta = d.estado_coeficientes([Decimal("50"), None])
    assert not falta.cuadra
    assert "1 unidad(es) sin coeficiente" in falta.mensaje
    assert "50,0000 %" in falta.mensaje


@pytest.mark.parametrize(
    ("vinculos", "esperado"),
    [
        ([], OcupacionUnidad.SIN_INFORMACION),
        ([(P, True)], OcupacionUnidad.PROPIETARIO),
        ([(P, False)], OcupacionUnidad.DESOCUPADA),
        ([(P, False), (A, True)], OcupacionUnidad.ARRENDADA),
        ([(P, False), (R_, True)], OcupacionUnidad.PROPIETARIO),  # vive la familia del propietario
        ([(AU, False)], OcupacionUnidad.SIN_INFORMACION),
    ],
)
def test_ocupacion_sugerida(vinculos: list[tuple[RelacionUnidad, bool]], esperado: OcupacionUnidad) -> None:
    assert d.ocupacion_sugerida(d.VinculoResumen(r, s) for r, s in vinculos) == esperado


def test_porcentajes_propiedad() -> None:
    d.validar_porcentajes_propiedad([Decimal(50), None, Decimal(50)])
    with pytest.raises(ValueError, match="más del 100"):
        d.validar_porcentajes_propiedad([Decimal(60), Decimal(41)])
