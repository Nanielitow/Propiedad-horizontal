"""Chunking consciente de páginas y secciones.

Unidad mínima = bloque (párrafo). Se acumulan bloques hasta ~max_tokens; cada
chunk recuerda la página donde empieza y donde termina (para la cita) y la
sección vigente ("CAPÍTULO III - De las mascotas"). Entre chunks consecutivos
se repiten los últimos bloques (~overlap_tokens) para no perder contexto en los
bordes.
"""

import re
from dataclasses import dataclass
from functools import lru_cache

import tiktoken

DEFAULT_MAX_TOKENS = 600
DEFAULT_OVERLAP_TOKENS = 80
_SEPARATOR = "\n\n"
_SEPARATOR_TOKENS = 1

_HEADING = re.compile(r"^(CAP[IÍ]TULO|T[IÍ]TULO|SECCI[OÓ]N|PARTE)\b", re.IGNORECASE)
_SENTENCE_END = re.compile(r"(?<=[.;:!?])\s+")


@dataclass(frozen=True)
class PageText:
    page_number: int
    blocks: list[str]


@dataclass(frozen=True)
class Chunk:
    index: int
    content: str
    page_number: int
    page_end: int
    token_count: int
    section_title: str | None


@dataclass(frozen=True)
class _Unit:
    text: str
    page: int
    tokens: int
    section: str | None
    starts_section: bool = False


@lru_cache
def _encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding("o200k_base")


def count_tokens(text: str) -> int:
    return len(_encoding().encode(text))


def is_heading(block: str) -> bool:
    if len(block) > 120:
        return False
    if _HEADING.match(block):
        return True
    letters = [c for c in block if c.isalpha()]
    # Línea corta mayoritariamente en MAYÚSCULAS con al menos 2 palabras
    return len(letters) >= 6 and len(block.split()) >= 2 and sum(c.isupper() for c in letters) / len(letters) > 0.8


def _split_long(text: str, max_tokens: int) -> list[str]:
    """Divide un bloque más largo que max_tokens: primero por oraciones y, si una
    oración sigue siendo enorme, por ventanas de palabras."""
    pieces: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for sentence in _SENTENCE_END.split(text):
        words = [sentence] if count_tokens(sentence) <= max_tokens else sentence.split()
        for part in words:
            t = count_tokens(part) + 1
            if current and current_tokens + t > max_tokens:
                pieces.append(" ".join(current))
                current, current_tokens = [], 0
            current.append(part)
            current_tokens += t
    if current:
        pieces.append(" ".join(current))
    return pieces


def _to_units(pages: list[PageText], max_tokens: int) -> list[_Unit]:
    units: list[_Unit] = []
    section: str | None = None
    for page in pages:
        for block in page.blocks:
            heading = is_heading(block)
            if heading:
                section = block
            pieces = [block] if count_tokens(block) <= max_tokens else _split_long(block, max_tokens)
            for i, piece in enumerate(pieces):
                units.append(_Unit(piece, page.page_number, count_tokens(piece), section, heading and i == 0))
    return units


def chunk_pages(
    pages: list[PageText],
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
    min_section_tokens: int | None = None,
) -> list[Chunk]:
    """min_section_tokens: al encontrar un encabezado (CAPÍTULO, TÍTULO...) se
    cierra el chunk actual si ya tiene al menos esos tokens. Así cada chunk
    pertenece a una sola sección y su cita apunta a la página correcta, en vez
    de mezclar capítulos de varias páginas. Por defecto max(25, max_tokens // 20):
    un título suelto no genera su propio chunk, un capítulo corto sí."""
    if overlap_tokens >= max_tokens:
        raise ValueError("overlap_tokens debe ser menor que max_tokens")
    min_section = max(25, max_tokens // 20) if min_section_tokens is None else min_section_tokens

    chunks: list[Chunk] = []
    buffer: list[_Unit] = []
    buffer_tokens = 0
    has_new_content = False  # evita emitir un chunk que sea solo solapamiento

    def emit() -> None:
        content = _SEPARATOR.join(u.text for u in buffer)
        chunks.append(
            Chunk(
                index=len(chunks),
                content=content,
                page_number=buffer[0].page,
                page_end=buffer[-1].page,
                token_count=count_tokens(content),
                section_title=buffer[0].section,
            )
        )

    for unit in _to_units(pages, max_tokens):
        cost = unit.tokens + _SEPARATOR_TOKENS
        if unit.starts_section and has_new_content and buffer_tokens >= min_section:
            # Nueva sección: corte limpio, sin solapamiento (el final del capítulo
            # anterior sería ruido para el siguiente)
            emit()
            buffer, buffer_tokens, has_new_content = [], 0, False
        elif buffer and buffer_tokens + cost > max_tokens:
            emit()
            # Solapamiento: últimos bloques que quepan en overlap_tokens
            tail: list[_Unit] = []
            tail_tokens = 0
            for prev in reversed(buffer):
                prev_cost = prev.tokens + _SEPARATOR_TOKENS
                if tail_tokens + prev_cost > overlap_tokens:
                    break
                tail.insert(0, prev)
                tail_tokens += prev_cost
            if tail_tokens + cost > max_tokens:  # el bloque nuevo no cabe con el solape
                tail, tail_tokens = [], 0
            buffer, buffer_tokens = tail, tail_tokens
            has_new_content = False
        buffer.append(unit)
        buffer_tokens += cost
        has_new_content = True

    if buffer and has_new_content:
        emit()
    return chunks
