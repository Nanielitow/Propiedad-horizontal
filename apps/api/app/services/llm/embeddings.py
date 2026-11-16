"""Proveedores de embeddings intercambiables (OpenAI, Gemini, fake)."""

import hashlib
import math
import re
from collections.abc import Iterator
from functools import lru_cache
from typing import Protocol

from app.core.config import Settings, get_settings
from app.models import EMBEDDING_DIM


class EmbeddingConfigError(RuntimeError):
    """Configuración inválida (falta API key, dimensión incorrecta...)."""


class Embedder(Protocol):
    model: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


def _batches(items: list[str], size: int) -> Iterator[list[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class OpenAIEmbedder:
    def __init__(self, settings: Settings) -> None:
        from openai import OpenAI

        if not settings.openai_api_key:
            raise EmbeddingConfigError("OPENAI_API_KEY no está configurada")
        self.model = settings.embedding_model
        self._dim = settings.embedding_dimensions
        self._client = OpenAI(api_key=settings.openai_api_key, max_retries=3, timeout=60)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for batch in _batches(texts, 128):
            resp = self._client.embeddings.create(model=self.model, input=batch, dimensions=self._dim)
            out.extend(d.embedding for d in sorted(resp.data, key=lambda d: d.index))
        return out

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


class GeminiEmbedder:
    """gemini-embedding-001 permite reducir a 1536 dims (Matryoshka). Con menos de
    3072 dims Google recomienda normalizar el vector, y se hace aquí."""

    def __init__(self, settings: Settings) -> None:
        from google import genai

        if not settings.gemini_api_key:
            raise EmbeddingConfigError("GEMINI_API_KEY no está configurada")
        self.model = settings.embedding_model
        self._dim = settings.embedding_dimensions
        self._client = genai.Client(api_key=settings.gemini_api_key)

    def _embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        from google.genai import types

        out: list[list[float]] = []
        for batch in _batches(texts, 100):
            resp = self._client.models.embed_content(
                model=self.model,
                contents=batch,
                config=types.EmbedContentConfig(task_type=task_type, output_dimensionality=self._dim),
            )
            out.extend(_normalize(list(e.values or [])) for e in resp.embeddings or [])
        return out

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, "RETRIEVAL_DOCUMENT")

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], "RETRIEVAL_QUERY")[0]


class FakeEmbedder:
    """Bolsa de palabras con hashing: determinista, gratis y sin red. Captura
    coincidencia léxica (no semántica). Solo para desarrollo y tests."""

    model = "fake-hash-v1"
    _word = re.compile(r"\w+", re.UNICODE)

    def __init__(self, dim: int = EMBEDDING_DIM) -> None:
        self._dim = dim

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self._dim
        for word in self._word.findall(text.lower()):
            h = hashlib.blake2b(word.encode(), digest_size=8).digest()
            idx = int.from_bytes(h[:4], "little") % self._dim
            vec[idx] += 1.0 if h[4] & 1 else -1.0
        return _normalize(vec)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


@lru_cache
def get_embedder() -> Embedder:
    settings = get_settings()
    if settings.embedding_dimensions != EMBEDDING_DIM:
        raise EmbeddingConfigError(
            f"EMBEDDING_DIMENSIONS={settings.embedding_dimensions} pero la columna es vector({EMBEDDING_DIM})"
        )
    if settings.embedding_provider == "openai":
        return OpenAIEmbedder(settings)
    if settings.embedding_provider == "gemini":
        return GeminiEmbedder(settings)
    return FakeEmbedder()
