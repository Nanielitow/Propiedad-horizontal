"""Modelos de chat intercambiables (Gemini, OpenAI) con streaming."""

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel

from app.core.config import Settings, get_settings

T = TypeVar("T", bound=BaseModel)
log = logging.getLogger(__name__)


class LLMConfigError(RuntimeError):
    """Falta API key o el proveedor no está configurado."""


class LLMError(RuntimeError):
    """Fallo del proveedor durante la generación (rate limit, caída, timeout)."""

    def __init__(self, message: str, *, retryable: bool = False, status: int | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status = status

    @property
    def quota_exceeded(self) -> bool:
        return self.status == 429


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["user", "assistant"]
    content: str


@dataclass
class Usage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    extra: dict[str, int] = field(default_factory=dict)


class ChatModel(Protocol):
    model: str

    def stream(
        self, system: str, messages: list[ChatMessage], usage: Usage, temperature: float = 0.2
    ) -> AsyncIterator[str]: ...

    async def complete(self, system: str, messages: list[ChatMessage], temperature: float = 0.0) -> str: ...


class StructuredModel(Protocol):
    """Modelo para extracción con Structured Outputs (respuesta validada contra un
    esquema Pydantic). Síncrono: se usa desde los workers de Celery."""

    model: str

    def extract(self, system: str, prompt: str, schema: type[T]) -> T: ...


class GeminiChat:
    def __init__(self, settings: Settings, model: str, thinking_level: str | None = None) -> None:
        from google import genai

        if not settings.gemini_api_key:
            raise LLMConfigError("GEMINI_API_KEY no está configurada")
        self.model = model
        self._thinking = (settings.chat_thinking_level if thinking_level is None else thinking_level).strip()
        self._client = genai.Client(api_key=settings.gemini_api_key)

    def extract(self, system: str, prompt: str, schema: type[T]) -> T:
        from google.genai import errors, types

        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    temperature=0,
                    response_mime_type="application/json",
                    response_schema=schema,
                ),
            )
        except errors.APIError as exc:
            raise self._wrap(exc) from exc
        if isinstance(response.parsed, schema):
            return response.parsed
        # Algunas respuestas llegan como texto JSON sin parsear
        return schema.model_validate_json(response.text or "{}")

    def _config(self, system: str, temperature: float):  # type: ignore[no-untyped-def]
        from google.genai import types

        extra = {}
        if self._thinking:
            extra["thinking_config"] = types.ThinkingConfig(thinking_level=self._thinking)  # type: ignore[arg-type]
        return types.GenerateContentConfig(system_instruction=system, temperature=temperature, **extra)

    @staticmethod
    def _contents(messages: list[ChatMessage]):  # type: ignore[no-untyped-def]
        from google.genai import types

        return [
            types.Content(role="model" if m.role == "assistant" else "user", parts=[types.Part(text=m.content)])
            for m in messages
        ]

    @staticmethod
    def _wrap(exc: Exception) -> LLMError:
        code = getattr(exc, "code", None)
        retryable = code in {429, 500, 502, 503, 504}
        return LLMError(f"Gemini {code}: {getattr(exc, 'message', exc)}", retryable=retryable, status=code)

    async def stream(
        self, system: str, messages: list[ChatMessage], usage: Usage, temperature: float = 0.2
    ) -> AsyncIterator[str]:
        from google.genai import errors

        try:
            response = await self._client.aio.models.generate_content_stream(
                model=self.model, contents=self._contents(messages), config=self._config(system, temperature)
            )
            async for chunk in response:
                if chunk.usage_metadata:
                    usage.prompt_tokens = chunk.usage_metadata.prompt_token_count
                    usage.completion_tokens = chunk.usage_metadata.candidates_token_count
                if chunk.text:
                    yield chunk.text
        except errors.APIError as exc:
            raise self._wrap(exc) from exc

    async def complete(self, system: str, messages: list[ChatMessage], temperature: float = 0.0) -> str:
        from google.genai import errors

        try:
            response = await self._client.aio.models.generate_content(
                model=self.model, contents=self._contents(messages), config=self._config(system, temperature)
            )
        except errors.APIError as exc:
            raise self._wrap(exc) from exc
        return (response.text or "").strip()


class OpenAIChat:
    def __init__(self, settings: Settings, model: str) -> None:
        from openai import AsyncOpenAI

        if not settings.openai_api_key:
            raise LLMConfigError("OPENAI_API_KEY no está configurada")
        self.model = model
        self._client = AsyncOpenAI(api_key=settings.openai_api_key, max_retries=2, timeout=60)

    @staticmethod
    def _messages(system: str, messages: list[ChatMessage]) -> list[dict[str, str]]:
        return [{"role": "system", "content": system}] + [{"role": m.role, "content": m.content} for m in messages]

    async def stream(
        self, system: str, messages: list[ChatMessage], usage: Usage, temperature: float = 0.2
    ) -> AsyncIterator[str]:
        from openai import APIError, APIStatusError

        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=self._messages(system, messages),  # type: ignore[arg-type]
                temperature=temperature,
                stream=True,
                stream_options={"include_usage": True},
            )
            async for event in response:
                if event.usage:
                    usage.prompt_tokens = event.usage.prompt_tokens
                    usage.completion_tokens = event.usage.completion_tokens
                if event.choices and event.choices[0].delta.content:
                    yield event.choices[0].delta.content
        except APIError as exc:
            status = exc.status_code if isinstance(exc, APIStatusError) else None
            raise LLMError(f"OpenAI {status}: {exc}", retryable=status in {429, 500, 502, 503}) from exc

    def extract(self, system: str, prompt: str, schema: type[T]) -> T:
        from openai import APIError, OpenAI

        client = OpenAI(api_key=self._client.api_key, max_retries=2, timeout=120)
        try:
            response = client.chat.completions.parse(
                model=self.model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                response_format=schema,
                temperature=0,
            )
        except APIError as exc:
            raise LLMError(f"OpenAI: {exc}", retryable=True) from exc
        parsed = response.choices[0].message.parsed
        if parsed is None:
            raise LLMError("OpenAI no devolvió una respuesta estructurada")
        return parsed

    async def complete(self, system: str, messages: list[ChatMessage], temperature: float = 0.0) -> str:
        from openai import APIError

        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=self._messages(system, messages),  # type: ignore[arg-type]
                temperature=temperature,
            )
        except APIError as exc:
            raise LLMError(f"OpenAI: {exc}") from exc
        return (response.choices[0].message.content or "").strip()


@lru_cache
def get_chat_model() -> ChatModel:
    settings = get_settings()
    if settings.llm_provider == "gemini":
        return GeminiChat(settings, settings.chat_model)
    return OpenAIChat(settings, settings.chat_model)


class FallbackStructuredModel:
    """Degradación controlada: si el modelo principal responde 429 (cuota agotada,
    p. ej. el límite diario del plan gratuito), se repite la extracción con el
    modelo de respaldo en lugar de dejar la tarea detenida. `model` refleja el que
    realmente respondió, para que quede registrado en el resultado."""

    def __init__(self, primary: StructuredModel, fallback: StructuredModel) -> None:
        self.primary = primary
        self.fallback = fallback
        self.model = primary.model

    def extract(self, system: str, prompt: str, schema: type[T]) -> T:
        try:
            return self.primary.extract(system, prompt, schema)
        except LLMError as exc:
            if not exc.quota_exceeded:
                raise
            log.warning("cuota agotada en %s; se usa el respaldo %s", self.primary.model, self.fallback.model)
            result = self.fallback.extract(system, prompt, schema)
            self.model = f"{self.fallback.model} (respaldo por cuota)"
            return result


def get_extraction_model() -> StructuredModel:
    """Modelo más capaz para extracciones en segundo plano: aquí la precisión
    importa más que la latencia (nadie espera mirando la pantalla). Con Gemini se
    deja el razonamiento interno en su valor por defecto (thinking_level=""), con
    el modelo del chat como respaldo si se agota la cuota.
    Sin caché: FallbackStructuredModel guarda qué modelo respondió en cada tarea."""
    settings = get_settings()
    if settings.llm_provider == "gemini":
        primary = GeminiChat(settings, settings.extraction_model, thinking_level="")
        if settings.chat_model == settings.extraction_model:
            return primary
        return FallbackStructuredModel(primary, GeminiChat(settings, settings.chat_model, thinking_level=""))
    return OpenAIChat(settings, settings.extraction_model)
