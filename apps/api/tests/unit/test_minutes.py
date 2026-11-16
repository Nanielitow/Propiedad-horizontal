from datetime import date
from typing import Any

from app.services.extraction.minutes import MinutesExtraction, verify_minutes

PAGES = {
    1: "Se verificó la asistencia de propietarios que representan el 72,3% de los coeficientes. "
    "El cambio de empresa obtuvo 64,1% a favor, 30,2% en contra y 5,7% de abstenciones. La propuesta queda APROBADA.",
    2: "La administradora presentará al consejo tres cotizaciones para la reparación de la fachada a más tardar "
    "el 30 de noviembre de 2026.",
}


def _extraction(**overrides: Any) -> MinutesExtraction:
    data: dict[str, Any] = {
        "assembly_type": "EXTRAORDINARIA",
        "assembly_date": "2026-10-18",
        "quorum_pct": 72.3,
        "quorum_page": 1,
        "quorum_quote": "representan el 72,3% de los coeficientes",
        "summary": "Asamblea extraordinaria.",
        "agreements": [],
        "votes": [
            {
                "topic": "Cambio de vigilancia",
                "yes_pct": 64.1,
                "no_pct": 30.2,
                "abstain_pct": 5.7,
                "result": "APROBADO",
                "page": 1,
                "quote": "La propuesta queda APROBADA.",
            }
        ],
        "tasks": [
            {
                "description": "Presentar tres cotizaciones de fachada",
                "assignee": "Administradora",
                "due_date": "2026-11-30",
                "page": 1,  # el modelo se equivoca de página: está en la 2
                "quote": "presentará al consejo tres cotizaciones para la reparación de la fachada",
            }
        ],
    }
    data.update(overrides)
    return MinutesExtraction.model_validate(data)


def test_votacion_y_quorum_verificados() -> None:
    r = verify_minutes(_extraction(), PAGES)
    assert r["quorum_pct"] == 72.3
    assert r["votes"][0]["verified"]
    assert r["assembly_date"] == date(2026, 10, 18)


def test_porcentaje_inventado_invalida_la_votacion() -> None:
    vote = _extraction().votes[0].model_copy(update={"yes_pct": 81.0})
    r = verify_minutes(_extraction(votes=[vote.model_dump()]), PAGES)
    assert not r["votes"][0]["verified"]


def test_quorum_que_no_esta_en_el_acta_no_se_muestra() -> None:
    assert verify_minutes(_extraction(quorum_pct=55.0), PAGES)["quorum_pct"] is None


def test_tarea_corrige_pagina_y_parsea_fecha() -> None:
    task = verify_minutes(_extraction(), PAGES)["tasks"][0]
    assert task["verified"] and task["page"] == 2
    assert task["due"] == date(2026, 11, 30)


def test_frase_inventada_queda_sin_verificar_pero_no_se_oculta() -> None:
    fake = {**_extraction().tasks[0].model_dump(), "quote": "el revisor fiscal auditará las cuentas del año"}
    r = verify_minutes(_extraction(tasks=[fake]), PAGES)
    assert len(r["tasks"]) == 1 and not r["tasks"][0]["verified"]
