"""Reglas puras de la cartera: cuotas, intereses, imputación de pagos, descuento y edades."""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.services.cartera import dominio as d
from app.services.cartera.cargos import partir_en_cuotas

D = Decimal


def test_redondeo() -> None:
    assert d.redondear(D("245349"), 100) == D("245300")
    assert d.redondear(D("245350"), 100) == D("245400")  # mitad hacia arriba
    assert d.redondear(D("1234.5"), 1) == D("1235")


def test_cuotas() -> None:
    # Presupuesto de $45.000.000 y coeficiente 1,8506 % -> $832.770 -> $832.800
    assert d.cuota_por_coeficiente(D("45000000"), D("1.8506"), 100) == D("832800")
    assert d.cuota_por_tipo({"APARTAMENTO": "250000"}, "APARTAMENTO", 100) == D("250000")
    assert d.cuota_por_tipo({"APARTAMENTO": "250000"}, "PARQUEADERO", 100) is None
    assert d.cuota_por_tipo({"PARQUEADERO": 0}, "PARQUEADERO", 100) is None


def test_intereses() -> None:
    assert d.interes_mora(D("500000"), D("1.5")) == D("7500")
    assert d.interes_mora(D("0"), D("1.5")) == 0
    assert d.interes_mora(D("500000"), D("0")) == 0


def test_fechas_periodo() -> None:
    f = d.fechas_periodo(2026, 2, 30, None)  # febrero no tiene 30
    assert f.vencimiento == date(2026, 2, 28) and f.limite_descuento is None
    f = d.fechas_periodo(2026, 11, 10, 5)
    assert f.vencimiento == date(2026, 11, 10) and f.limite_descuento == date(2026, 11, 5)
    assert d.nombre_periodo(2026, 11) == "noviembre de 2026"
    assert d.fin_de_mes(date(2028, 2, 3)) == date(2028, 2, 29)


def _c(
    nombre: str,
    venc: date,
    saldo: str,
    *,
    interes: bool = False,
    valor: str | None = None,
    pct: str | None = None,
    limite: date | None = None,
) -> d.CargoPendiente:
    return d.CargoPendiente(
        id=uuid.uuid5(uuid.NAMESPACE_OID, nombre),
        es_interes=interes,
        fecha_vencimiento=venc,
        fecha_causacion=venc,
        valor=D(valor or saldo),
        saldo=D(saldo),
        descuento_pct=D(pct) if pct else None,
        fecha_limite_descuento=limite,
    )


ID = lambda n: uuid.uuid5(uuid.NAMESPACE_OID, n)  # noqa: E731


def test_imputa_intereses_primero_y_luego_lo_mas_antiguo() -> None:
    cargos = [
        _c("nov", date(2026, 11, 10), "300000"),
        _c("oct", date(2026, 10, 10), "300000"),
        _c("int", date(2026, 11, 10), "4500", interes=True),
    ]
    r = d.imputar(D("350000"), cargos, date(2026, 11, 20))
    assert r.aplicaciones == [(ID("int"), D("4500")), (ID("oct"), D("300000")), (ID("nov"), D("45500"))]
    assert r.sobrante == 0 and r.descuentos == []


def test_sobrante_queda_a_favor() -> None:
    r = d.imputar(D("400000"), [_c("nov", date(2026, 11, 10), "300000")], date(2026, 11, 1))
    assert r.aplicado == D("300000") and r.sobrante == D("100000")


def test_descuento_por_pronto_pago() -> None:
    cuota = _c("nov", date(2026, 11, 10), "300000", pct="10", limite=date(2026, 11, 5))
    # A tiempo y alcanza para la cuota con descuento: paga 270.000 y se rebajan 30.000
    r = d.imputar(D("270000"), [cuota], date(2026, 11, 5))
    assert r.aplicaciones == [(ID("nov"), D("270000"))] and r.descuentos == [(ID("nov"), D("30000"))]
    # Tarde: sin descuento, abono parcial
    r = d.imputar(D("270000"), [cuota], date(2026, 11, 6))
    assert r.descuentos == [] and r.aplicaciones == [(ID("nov"), D("270000"))]
    # A tiempo pero no alcanza: sin descuento
    r = d.imputar(D("200000"), [cuota], date(2026, 11, 3))
    assert r.descuentos == []


def test_sin_descuento_si_debe_meses_anteriores() -> None:
    vieja = _c("oct", date(2026, 10, 10), "300000")
    cuota = _c("nov", date(2026, 11, 10), "300000", pct="10", limite=date(2026, 11, 5))
    # Paga solo la cuota del mes: se imputa a la deuda vieja, y no hay descuento
    r = d.imputar(D("270000"), [vieja, cuota], date(2026, 11, 2))
    assert r.descuentos == [] and r.aplicaciones == [(ID("oct"), D("270000"))]
    # Paga todo lo vencido + la cuota con descuento: sí aplica
    r = d.imputar(D("570000"), [vieja, cuota], date(2026, 11, 2))
    assert r.descuentos == [(ID("nov"), D("30000"))] and r.sobrante == 0


def test_descuento_no_aplica_a_cuota_ya_abonada() -> None:
    abonada = _c("nov", date(2026, 11, 10), "100000", valor="300000", pct="10", limite=date(2026, 11, 5))
    assert d.imputar(D("100000"), [abonada], date(2026, 11, 1)).descuentos == []


def test_edades() -> None:
    corte = date(2026, 11, 24)
    r = d.edades(
        [
            (date(2026, 12, 10), D("100")),  # aún no vence
            (date(2026, 11, 10), D("200")),  # 14 días
            (date(2026, 10, 10), D("300")),  # 45 días
            (date(2026, 9, 10), D("400")),  # 75 días
            (date(2026, 6, 10), D("500")),  # 167 días
            (date(2026, 5, 10), D("0")),
        ],
        corte,
    )
    assert r == {"corriente": D("100"), "1_30": D("200"), "31_60": D("300"), "61_90": D("400"), "mas_90": D("500")}


@pytest.mark.parametrize(
    ("valor", "n", "esperado"),
    [("1000000", 3, ["333300", "333300", "333400"]), ("500000", 1, ["500000"]), ("100000", 4, ["25000"] * 4)],
)
def test_partir_en_cuotas(valor: str, n: int, esperado: list[str]) -> None:
    partes = partir_en_cuotas(D(valor), n, 100)
    assert partes == [D(x) for x in esperado] and sum(partes) == D(valor)


def test_codigo_verificacion() -> None:
    c = d.codigo_verificacion()
    assert len(c) == 14 and c[4] == c[9] == "-"
    assert not set(c.replace("-", "")) & set("01OI")
    assert d.codigo_verificacion() != c
