"""OCR con ocrmypdf + Tesseract (español).

Genera un PDF NUEVO con capa de texto invisible sobre la imagen original:
- el pipeline vuelve a extraer texto de él con PyMuPDF (mismo código que nativo)
- el visor del frontend muestra ese PDF, así el texto escaneado es seleccionable
"""

from pathlib import Path

import ocrmypdf
from ocrmypdf.exceptions import EncryptedPdfError, InputFileError

from app.services.ingestion.errors import PermanentIngestionError


def ocr_pdf(src: Path, dest: Path) -> None:
    try:
        ocrmypdf.ocr(
            src,
            dest,
            language=["spa"],
            skip_text=True,  # solo OCR en páginas SIN texto (PDF mixtos)
            rotate_pages=True,  # corrige páginas escaneadas de lado
            deskew=True,  # endereza escaneos torcidos
            optimize=0,
            progress_bar=False,
            use_threads=True,  # los procesos de Celery (prefork) no pueden crear subprocesos de multiprocessing
        )
    except EncryptedPdfError as exc:
        raise PermanentIngestionError("El PDF está cifrado y no se puede aplicar OCR") from exc
    except InputFileError as exc:
        raise PermanentIngestionError(f"PDF inválido para OCR: {exc}") from exc
