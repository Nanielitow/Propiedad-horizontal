"""Extracción de texto nativo por página con PyMuPDF.

Se extrae por BLOQUES (párrafos según el layout del PDF), no por líneas: así el
chunker corta entre párrafos y no a mitad de una frase.
"""

import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from app.models.enums import ExtractionMethod
from app.services.ingestion.errors import PermanentIngestionError

# Menos caracteres que esto => la página es una imagen (escaneada) y requiere OCR
MIN_NATIVE_CHARS = 25

_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int
    blocks: list[str]
    method: ExtractionMethod = ExtractionMethod.NATIVE

    @property
    def text(self) -> str:
        return "\n\n".join(self.blocks)

    @property
    def needs_ocr(self) -> bool:
        return len(self.text.strip()) < MIN_NATIVE_CHARS


def clean_block(raw: str) -> str:
    text = raw.replace("\x00", "")  # Postgres rechaza NUL en columnas text
    text = _HYPHEN_BREAK.sub(r"\1\2", text)  # "manteni-\nmiento" -> "mantenimiento"
    return _WHITESPACE.sub(" ", text).strip()


def extract_pages(pdf_path: Path) -> list[ExtractedPage]:
    try:
        doc = pymupdf.open(pdf_path)
    except (pymupdf.FileDataError, RuntimeError) as exc:
        raise PermanentIngestionError(f"El archivo no es un PDF válido: {exc}") from exc

    with doc:
        if doc.needs_pass:
            raise PermanentIngestionError("El PDF está protegido con contraseña")
        pages: list[ExtractedPage] = []
        for number, page in enumerate(doc, start=1):
            # get_text("blocks") -> (x0, y0, x1, y1, texto, nº bloque, tipo); tipo 0 = texto
            blocks = [
                cleaned for b in page.get_text("blocks", sort=True) if b[6] == 0 and (cleaned := clean_block(b[4]))
            ]
            pages.append(ExtractedPage(page_number=number, blocks=blocks))
    return pages
