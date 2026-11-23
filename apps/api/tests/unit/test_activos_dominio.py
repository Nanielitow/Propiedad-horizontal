import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.models.enums import EstadoNovedad, Periodicidad
from app.services.activos.dominio import (
    TRANSICIONES_NOVEDAD,
    estado_por_horas,
    fechas_programables,
    nuevo_qr_token,
    ocurrencia,
    peor_color,
    semaforo,
    siguiente_fecha,
    sumar_meses,
    vida_util_consumida,
)

P = Periodicidad
SQL = Path(__file__).resolve().parents[2] / "alembic" / "sql" / "0005_activos.up.sql"
HOY = date(2026, 11, 20)


def test_sumar_meses_ajusta_fin_de_mes() -> None:
    assert sumar_meses(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert sumar_meses(date(2028, 1, 31), 1) == date(2028, 2, 29)  # bisiesto
    assert sumar_meses(date(2026, 11, 15), 3) == date(2027, 2, 15)


def test_las_fechas_se_calculan_desde_el_inicio_sin_arrastrar_el_ajuste() -> None:
    # Si se encadenara (31 ene -> 28 feb -> 28 mar), marzo quedaría en 28: debe volver a 31
    assert [ocurrencia(date(2026, 1, 31), P.MENSUAL, k) for k in range(3)] == [
        date(2026, 1, 31),
        date(2026, 2, 28),
        date(2026, 3, 31),
    ]


@pytest.mark.parametrize(
    ("periodicidad", "siguiente"),
    [
        (P.SEMANAL, date(2026, 11, 27)),
        (P.QUINCENAL, date(2026, 12, 5)),
        (P.MENSUAL, date(2026, 12, 20)),
        (P.BIMESTRAL, date(2027, 1, 20)),
        (P.TRIMESTRAL, date(2027, 2, 20)),
        (P.SEMESTRAL, date(2027, 5, 20)),
        (P.ANUAL, date(2027, 11, 20)),
    ],
)
def test_siguiente_fecha_por_periodicidad(periodicidad: Periodicidad, siguiente: date) -> None:
    assert siguiente_fecha(HOY, periodicidad) == siguiente


def test_fechas_programables_en_un_horizonte() -> None:
    fechas = fechas_programables(date(2026, 1, 5), P.MENSUAL, desde=HOY, hasta=sumar_meses(HOY, 12))
    assert fechas[0] == date(2026, 12, 5)  # la primera futura, no las pasadas
    assert len(fechas) == 12
    assert fechas[-1] == date(2027, 11, 5)
    with pytest.raises(ValueError, match="horas de uso"):
        ocurrencia(HOY, P.POR_HORAS_USO, 1)


@pytest.mark.parametrize(
    ("dias", "color"),
    [(16, "VERDE"), (15, "AMARILLO"), (1, "AMARILLO"), (0, "AMARILLO"), (-1, "ROJO"), (-30, "ROJO")],
)
def test_semaforo(dias: int, color: str) -> None:
    from datetime import timedelta

    assert semaforo(HOY + timedelta(days=dias), HOY) == (color, dias)


def test_el_semaforo_del_activo_es_el_peor_color() -> None:
    assert peor_color(["VERDE", "ROJO", "AMARILLO"]) == "ROJO"
    assert peor_color(["VERDE", "AMARILLO"]) == "AMARILLO"
    assert peor_color([]) is None


def test_plan_por_horas_de_uso() -> None:
    e = estado_por_horas(250, Decimal(200), Decimal(10), HOY)
    assert (e.horas_restantes, e.color, e.fecha_estimada) == (Decimal(50), "VERDE", date(2026, 11, 25))
    assert estado_por_horas(250, Decimal(230), Decimal(10), HOY).color == "AMARILLO"  # menos del 10 %
    assert estado_por_horas(250, Decimal(260), None, HOY).color == "ROJO"
    assert estado_por_horas(250, Decimal(10), None, HOY).fecha_estimada is None  # sin uso medido


def test_vida_util_consumida() -> None:
    assert vida_util_consumida(date(2016, 11, 20), 20, HOY) == Decimal("50.0")
    assert vida_util_consumida(None, 20, HOY) is None


def test_token_qr_aleatorio_y_seguro_para_url() -> None:
    tokens = {nuevo_qr_token() for _ in range(100)}
    assert len(tokens) == 100
    assert all(re.fullmatch(r"[A-Za-z0-9_-]{32}", t) for t in tokens)


def test_flujo_de_novedades_coincide_con_el_trigger() -> None:
    sql = SQL.read_text(encoding="utf-8")
    inicio = sql.index("IF v_transicion NOT IN")
    bloque = sql[inicio : sql.index("THEN", inicio)]
    en_sql = set(re.findall(r"'([A-Z_]+>[A-Z_]+)'", bloque))
    en_python = {f"{o}>{d}" for o, destinos in TRANSICIONES_NOVEDAD.items() for d in destinos}
    assert en_sql == en_python
    assert TRANSICIONES_NOVEDAD[EstadoNovedad.CERRADA] == frozenset()
