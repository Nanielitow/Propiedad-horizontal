from typing import Any

from app.services.extraction.quotes import (
    QuoteExtraction,
    compute_best,
    facts_for_analysis,
    numbers_in,
    parse_number,
    verify_extraction,
)


def test_parse_number_formatos_colombiano_e_internacional() -> None:
    assert parse_number("48.500.000") == 48_500_000
    assert parse_number("48,500,000") == 48_500_000
    assert parse_number("48.500.000,00") == 48_500_000
    assert parse_number("48,500,000.50") == 48_500_000
    assert parse_number("48500000") == 48_500_000
    assert parse_number("19,5") == 19  # coma decimal
    assert parse_number("4.5") == 4  # punto decimal


def test_numbers_in_texto() -> None:
    assert {40_756_303, 7_743_697, 48_500_000, 19} <= numbers_in(
        "Valor antes de IVA: $40.756.303. IVA (19%): $7.743.697. VALOR TOTAL: $48.500.000."
    )


PAGES = {
    1: "Valor de la obra: $44.700.000 más IVA del 19%. Garantía de diez (10) años sobre la membrana.",
    2: "Plazo: veinte (20) días hábiles.",
}


def _extraction(**overrides: Any) -> QuoteExtraction:
    data: dict[str, Any] = {
        "provider_name": "Techos Pro",
        "subtotal": {"value": 44_700_000, "page": 1, "quote": "Valor de la obra: $44.700.000 más IVA del 19%"},
        "tax": {"value": 8_493_000, "page": None, "quote": None},
        "total": {"value": 53_193_000, "page": None, "quote": None},
        "total_computed": True,
        "warranty": {"value": "10 años", "page": 1, "quote": "Garantía de diez (10) años sobre la membrana"},
        "warranty_months": 120,
        "delivery": {"value": "20 días hábiles", "page": 1, "quote": "Plazo: veinte (20) días hábiles."},
        "delivery_days": 20,
        "delivery_business_days": True,
        "payment_terms": {},
        "valid_until": {},
        "includes": [],
        "excludes": [],
        "items": [],
    }
    data.update(overrides)
    return QuoteExtraction.model_validate(data)


def test_total_calculado_se_verifica_por_la_suma() -> None:
    record = verify_extraction(_extraction(), PAGES)
    assert record["subtotal"]["verified"]
    assert record["total"]["verified"] and record["total"]["computed"]


def test_iva_calculado_con_la_tasa_del_documento() -> None:
    record = verify_extraction(_extraction(), PAGES)
    assert record["tax"]["verified"] and record["tax"]["computed"] and record["tax"]["rate"] == 19


def test_iva_con_tasa_que_no_aparece_no_se_verifica() -> None:
    record = verify_extraction(_extraction(tax={"value": 2_235_000}), PAGES)  # 5 % no está en el texto
    assert not record["tax"]["verified"]


def test_total_inventado_queda_sin_verificar() -> None:
    record = verify_extraction(_extraction(total={"value": 51_000_000, "page": 1, "quote": "x"}), PAGES)
    assert not record["total"]["verified"]


def test_texto_verificado_corrige_pagina() -> None:
    record = verify_extraction(_extraction(), PAGES)
    assert record["delivery"]["verified"] and record["delivery"]["page"] == 2


def test_texto_sin_frase_no_se_verifica() -> None:
    record = verify_extraction(
        _extraction(warranty={"value": "20 años", "page": 1, "quote": "garantía de veinte años"}), PAGES
    )
    assert not record["warranty"]["verified"]


def test_datos_ausentes_llegan_al_analisis_como_no_indicados() -> None:
    record = verify_extraction(_extraction(tax={"value": None}), PAGES)
    facts = facts_for_analysis(record)
    assert facts["tax"] == "no indicado en la cotización"
    assert facts["subtotal"] == {"valor": 44_700_000, "confirmado_en_el_documento": True}
    assert "items" not in facts


def _rec(total: float | None, warranty: int | None, days: int | None, business: bool = False) -> dict[str, Any]:
    return {
        "total": {"value": total},
        "warranty_months": warranty,
        "delivery_days": days,
        "delivery_business_days": business,
    }


def test_compute_best_por_criterio() -> None:
    best = compute_best(
        {
            "a": _rec(48_500_000, 60, 25, business=True),  # 35 días calendario
            "b": _rec(42_900_000, 36, 35),
            "c": _rec(53_193_000, 120, 20, business=True),  # 28 días calendario
        }
    )
    assert best["total"] == "b"
    assert best["warranty"] == "c"
    assert best["delivery"] == "c"
    assert best["min_total"] == 42_900_000 and best["max_total"] == 53_193_000


def test_compute_best_sin_ganador_en_empate_o_sin_datos() -> None:
    best = compute_best({"a": _rec(10, None, None), "b": _rec(10, 12, None)})
    assert best["total"] is None  # empate
    assert best["warranty"] is None  # solo un valor
