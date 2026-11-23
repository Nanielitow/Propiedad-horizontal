import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.models.enums import EstadoRecaudo, MedioPago, TipoCobro
from app.schemas.recaudos import ParqueaderoIn, normalizar_placa
from app.services.recaudos.dominio import (
    TRANSICIONES,
    TransicionInvalida,
    ValidacionError,
    calcular_parqueadero,
    es_mismo_dia_bogota,
    estado_inicial,
    validar_transicion,
    valor_por_defecto,
)

E = EstadoRecaudo
T0 = datetime(2026, 11, 20, 14, 0, tzinfo=UTC)
SQL = Path(__file__).resolve().parents[2] / "alembic" / "sql" / "0003_recaudos.up.sql"


@pytest.mark.parametrize(
    ("minutos", "fracciones", "tarifa"),
    [(1, 1, "2000.00"), (60, 1, "2000.00"), (61, 2, "4000.00"), (150, 3, "6000.00"), (24 * 60, 24, "48000.00")],
)
def test_parqueadero_cobra_por_fraccion_iniciada(minutos: int, fracciones: int, tarifa: str) -> None:
    calc = calcular_parqueadero(T0, T0 + timedelta(minutes=minutos), Decimal(2000), 60)
    assert (calc.minutos, calc.fracciones, calc.tarifa_sugerida) == (minutos, fracciones, Decimal(tarifa))


def test_parqueadero_redondea_segundos_hacia_arriba_como_la_columna_generada() -> None:
    calc = calcular_parqueadero(T0, T0 + timedelta(minutes=60, seconds=1), Decimal(2000), 60)
    assert calc.minutos == 61
    assert calc.fracciones == 2


def test_parqueadero_con_fraccion_de_media_hora() -> None:
    calc = calcular_parqueadero(T0, T0 + timedelta(minutes=45), Decimal(1000), 30)
    assert calc.tarifa_sugerida == Decimal("2000.00")


def test_parqueadero_rechaza_salida_anterior() -> None:
    with pytest.raises(ValidacionError):
        calcular_parqueadero(T0, T0, Decimal(2000), 60)


@pytest.mark.parametrize(
    ("entrada", "esperada"), [("abc-123", "ABC123"), (" ABC 12d ", "ABC12D"), ("xyz.987", "XYZ987")]
)
def test_normalizar_placa(entrada: str, esperada: str) -> None:
    assert normalizar_placa(entrada) == esperada


@pytest.mark.parametrize("invalida", ["AB1", "ABC-12345", "ÑAN123", ""])
def test_placa_invalida(invalida: str) -> None:
    with pytest.raises(ValueError, match="Placa inválida"):
        normalizar_placa(invalida)


def test_parqueadero_exige_zona_horaria() -> None:
    with pytest.raises(ValueError, match="zona horaria"):
        ParqueaderoIn(placa_vehiculo="ABC123", hora_ingreso=datetime(2026, 1, 1, 8), hora_salida=T0)


def test_estado_inicial_segun_medio_de_pago() -> None:
    assert estado_inicial(MedioPago.EFECTIVO) == E.RECAUDADO_EN_CAJA
    assert estado_inicial(MedioPago.TRANSFERENCIA) == E.PENDIENTE_VERIFICACION
    assert estado_inicial(MedioPago.CONSIGNACION) == E.PENDIENTE_VERIFICACION


def test_anulado_es_final() -> None:
    for destino in E:
        with pytest.raises(TransicionInvalida):
            validar_transicion(E.ANULADO, destino)


def test_transferencia_no_pasa_por_caja() -> None:
    with pytest.raises(TransicionInvalida):
        validar_transicion(E.PENDIENTE_VERIFICACION, E.CONSIGNADO)
    validar_transicion(E.PENDIENTE_VERIFICACION, E.VERIFICADO)


def test_maquina_de_estados_coincide_con_el_trigger_de_la_base() -> None:
    """La lista de transiciones del trigger trg_recaudos_update debe ser idéntica a la de Python."""
    sql = SQL.read_text(encoding="utf-8")
    bloque = sql[sql.index("IF v_transicion NOT IN") : sql.index("THEN", sql.index("IF v_transicion NOT IN"))]
    en_sql = set(re.findall(r"'([A-Z_]+>[A-Z_]+)'", bloque))
    en_python = {f"{origen}>{destino}" for origen, destinos in TRANSICIONES.items() for destino in destinos}
    assert en_sql == en_python


def test_valor_por_defecto_solo_en_cobros_fijos() -> None:
    assert valor_por_defecto(TipoCobro.FIJO, Decimal(50000)) == Decimal(50000)
    assert valor_por_defecto(TipoCobro.VARIABLE, Decimal(50000)) is None
    assert valor_por_defecto(TipoCobro.FIJO, None) is None


def test_mismo_dia_en_hora_de_bogota() -> None:
    # 23:30 del 20 en Bogotá = 04:30 UTC del 21: sigue siendo el mismo día local
    noche = datetime(2026, 11, 21, 4, 30, tzinfo=UTC)
    tarde = datetime(2026, 11, 20, 20, 0, tzinfo=UTC)
    assert es_mismo_dia_bogota(noche, tarde)
    assert not es_mismo_dia_bogota(noche, datetime(2026, 11, 21, 14, 0, tzinfo=UTC))
