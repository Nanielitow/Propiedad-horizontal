"""Reglas puras del portal: festivos colombianos, días hábiles, reglas de reserva y estados de PQRS."""

from datetime import date, time

import pytest

from app.models.enums import EstadoPqrs
from app.services.portal import dominio as d

E = EstadoPqrs


def test_festivos_2026_segun_calendario_oficial() -> None:
    esperados = {
        date(2026, 1, 1), date(2026, 1, 12), date(2026, 3, 23), date(2026, 4, 2), date(2026, 4, 3),
        date(2026, 5, 1), date(2026, 5, 18), date(2026, 6, 8), date(2026, 6, 15), date(2026, 6, 29),
        date(2026, 7, 20), date(2026, 8, 7), date(2026, 8, 17), date(2026, 10, 12), date(2026, 11, 2),
        date(2026, 11, 16), date(2026, 12, 8), date(2026, 12, 25),
    }  # fmt: skip
    assert d.festivos(2026) == esperados


def test_pascua() -> None:
    assert d._pascua(2026) == date(2026, 4, 5)
    assert d._pascua(2027) == date(2027, 3, 28)
    assert d._pascua(2024) == date(2024, 3, 31)


def test_dias_habiles() -> None:
    assert not d.es_habil(date(2026, 11, 28))  # sábado
    assert not d.es_habil(date(2026, 11, 16))  # festivo (Independencia de Cartagena)
    assert d.es_habil(date(2026, 11, 24))
    # Radicada el martes 24 de noviembre de 2026: 15 días hábiles (8 de diciembre es festivo)
    assert d.sumar_dias_habiles(date(2026, 11, 24), 15) == date(2026, 12, 16)
    assert d.dias_habiles_entre(date(2026, 11, 24), date(2026, 12, 16)) == 15
    assert d.dias_habiles_entre(date(2026, 12, 16), date(2026, 11, 24)) == -15
    assert d.dias_habiles_entre(date(2026, 11, 24), date(2026, 11, 24)) == 0


REGLAS = d.ReglasZona(time(8), time(22), 2, 60, 2, 40)


@pytest.mark.parametrize(
    ("fecha", "hi", "hf", "asist", "mes", "error"),
    [
        (date(2026, 11, 25), time(10), time(14), 10, 0, "al menos 2 día"),
        (date(2026, 11, 20), time(10), time(14), 10, 0, "ya pasó"),
        (date(2027, 3, 1), time(10), time(14), 10, 0, "hasta 60 días"),
        (date(2026, 12, 5), time(7), time(14), 10, 0, "funciona de 08:00 a 22:00"),
        (date(2026, 12, 5), time(14), time(10), 10, 0, "posterior a la de inicio"),
        (date(2026, 12, 5), time(10), time(14), 50, 0, "capacidad máxima es de 40"),
        (date(2026, 12, 5), time(10), time(14), 10, 2, "ya tiene 2 reserva"),
        (date(2026, 12, 5), None, None, None, 0, "hora de inicio y de fin"),
    ],
)
def test_reglas_de_reserva(
    fecha: date, hi: time | None, hf: time | None, asist: int | None, mes: int, error: str
) -> None:
    errores = d.validar_reserva(
        REGLAS, hoy=date(2026, 11, 24), fecha=fecha, hora_inicio=hi, hora_fin=hf, asistentes=asist, reservas_del_mes=mes
    )
    assert any(error in e for e in errores), errores


def test_reserva_valida() -> None:
    assert (
        d.validar_reserva(
            REGLAS,
            hoy=date(2026, 11, 24),
            fecha=date(2026, 12, 5),
            hora_inicio=time(14),
            hora_fin=time(20),
            asistentes=30,
            reservas_del_mes=1,
        )
        == []
    )


def test_transiciones_pqrs() -> None:
    assert d.puede_pasar(E.RADICADA, E.EN_TRAMITE)
    assert d.puede_pasar(E.RESPONDIDA, E.EN_TRAMITE)  # reabierta por el residente
    assert not d.puede_pasar(E.RADICADA, E.CERRADA)  # no se cierra sin responder
    assert not d.puede_pasar(E.CERRADA, E.EN_TRAMITE)
    assert d.ABIERTAS == {E.RADICADA, E.EN_TRAMITE}
