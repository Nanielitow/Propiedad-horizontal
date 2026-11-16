import pytest
from pydantic import BaseModel

from app.services.llm.chat import FallbackStructuredModel, LLMError


class Out(BaseModel):
    value: str


class FakeModel:
    def __init__(self, name: str, error: LLMError | None = None) -> None:
        self.model = name
        self.error = error
        self.calls = 0

    def extract(self, system: str, prompt: str, schema: type[Out]) -> Out:
        self.calls += 1
        if self.error:
            raise self.error
        return schema(value=self.model)


def test_usa_el_principal_si_responde() -> None:
    primary, fallback = FakeModel("flash"), FakeModel("lite")
    model = FallbackStructuredModel(primary, fallback)
    assert model.extract("s", "p", Out).value == "flash"
    assert fallback.calls == 0 and model.model == "flash"


def test_cuota_agotada_pasa_al_respaldo_y_lo_registra() -> None:
    primary = FakeModel("flash", LLMError("Gemini 429: quota", retryable=True, status=429))
    fallback = FakeModel("lite")
    model = FallbackStructuredModel(primary, fallback)
    assert model.extract("s", "p", Out).value == "lite"
    assert model.model == "lite (respaldo por cuota)"


def test_otros_errores_no_activan_el_respaldo() -> None:
    primary = FakeModel("flash", LLMError("Gemini 503: overloaded", retryable=True, status=503))
    fallback = FakeModel("lite")
    with pytest.raises(LLMError):
        FallbackStructuredModel(primary, fallback).extract("s", "p", Out)
    assert fallback.calls == 0  # 503 se reintenta con backoff, no se degrada la calidad
