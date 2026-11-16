from datetime import date

from app.services.extraction.deadlines import (
    DeadlineCandidate,
    add_months,
    locate_quote,
    parse_date,
    verify,
)

TODAY = date(2026, 11, 15)
PAGES = {
    1: "PÓLIZA DE SEGURO DE ÁREAS COMUNES. Aseguradora: Seguros Bolívar S.A.",
    2: "Vigencia: desde las 00:00 horas del 1 de abril de 2026 hasta las 24:00 horas del 31 de marzo de 2027.",
}


def _candidate(**overrides: object) -> DeadlineCandidate:
    data: dict[str, object] = {
        "title": "Póliza de áreas comunes",
        "type": "POLICY_EXPIRY",
        "due_date": "2027-03-31",
        "page_number": 2,
        "source_quote": "hasta las 24:00 horas del 31 de marzo de 2027",
        "confidence": 0.95,
    }
    data.update(overrides)
    return DeadlineCandidate.model_validate(data)


# -- Localización de la frase de origen --------------------------------------
def test_frase_exacta_aunque_cambien_tildes_y_puntuacion() -> None:
    match = locate_quote("HASTA LAS 24:00 HORAS DEL 31 DE MARZO DE 2027", PAGES, hinted_page=2)
    assert match is not None and match.page == 2 and match.exact


def test_corrige_la_pagina_si_el_modelo_se_equivoca() -> None:
    match = locate_quote("hasta las 24:00 horas del 31 de marzo de 2027", PAGES, hinted_page=1)
    assert match is not None and match.page == 2


def test_tolera_pequenas_diferencias_de_ocr() -> None:
    # Una palabra mal reconocida ("h0ras") de 10: cobertura 90 % >= 85 %
    pages = {1: "Vigencia desde las 00:00 h0ras del 1 de abril de 2026 hasta las 24:00 horas del 31 de marzo de 2027"}
    match = locate_quote("desde las 00:00 horas del 1 de abril de 2026 hasta las 24:00 horas", pages, hinted_page=1)
    assert match is not None and not match.exact


def test_rechaza_frases_inventadas() -> None:
    assert locate_quote("la póliza vence el 15 de junio de 2027 sin renovación", PAGES, hinted_page=2) is None


def test_rechaza_frases_demasiado_cortas() -> None:
    assert locate_quote("2027", PAGES, hinted_page=2) is None


# -- Verificación completa ----------------------------------------------------
def test_acepta_candidato_verificado() -> None:
    accepted, rejected = verify([_candidate()], PAGES, TODAY)
    assert rejected == []
    assert accepted[0].due_date == date(2027, 3, 31)
    assert accepted[0].page == 2
    assert float(accepted[0].confidence) == 0.95


def test_rechaza_alucinacion() -> None:
    accepted, rejected = verify([_candidate(source_quote="vence el 15 de junio de 2027 sin renovación")], PAGES, TODAY)
    assert accepted == [] and "no está en el documento" in rejected[0][1]


def test_rechaza_fecha_invalida_o_muy_pasada() -> None:
    _, rejected = verify([_candidate(due_date="31/03/2027"), _candidate(due_date="2025-01-10")], PAGES, TODAY)
    assert [r for _, r in rejected] == ["fecha inválida", "fecha ya pasada"]


def test_coincidencia_aproximada_reduce_la_confianza() -> None:
    pages = {1: "Vigencia desde las 00:00 h0ras del 1 de abril de 2026 hasta las 24:00 horas del 31 de marzo de 2027"}
    accepted, _ = verify(
        [_candidate(source_quote="desde las 00:00 horas del 1 de abril de 2026 hasta las 24:00 horas", confidence=1.0)],
        pages,
        TODAY,
    )
    assert float(accepted[0].confidence) == 0.9


def test_limita_recurrencias_absurdas() -> None:
    accepted, _ = verify([_candidate(recurrence_months=999)], PAGES, TODAY)
    assert accepted[0].candidate.recurrence_months is None


# -- Fechas -------------------------------------------------------------------
def test_add_months_ajusta_fin_de_mes() -> None:
    assert add_months(date(2027, 1, 31), 1) == date(2027, 2, 28)
    assert add_months(date(2028, 1, 31), 1) == date(2028, 2, 29)  # bisiesto
    assert add_months(date(2026, 9, 10), 6) == date(2027, 3, 10)
    assert add_months(date(2026, 11, 30), 14) == date(2028, 1, 30)


def test_parse_date() -> None:
    assert parse_date("2027-03-31") == date(2027, 3, 31)
    assert parse_date("2027-03-31T00:00:00") == date(2027, 3, 31)
    assert parse_date("31 de marzo") is None
    assert parse_date(None) is None
