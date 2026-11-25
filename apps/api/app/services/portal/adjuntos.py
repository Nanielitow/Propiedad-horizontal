"""Adjuntos del portal (fotos o PDF de una PQRS): URL firmada, subida directa y validación.

Una clave solo se acepta si está en la carpeta de la copropiedad y el archivo ya existe:
así nadie adjunta archivos de otra copropiedad ni claves inventadas.
"""

import re
from dataclasses import dataclass
from typing import Any

from fastapi.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.schemas.portal import Adjunto
from app.services.comun import Actor, ValidacionError
from app.services.storage.s3 import get_storage

TIPOS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "application/pdf": "pdf"}
MIME = {v: k for k, v in TIPOS.items()}
_CLAVE = re.compile(r"^tenants/(?P<tenant>[0-9a-f-]{36})/portal/adjuntos/[0-9a-f-]{36}\.(?P<ext>jpg|png|webp|pdf)$")


@dataclass(frozen=True)
class UrlSubida:
    storage_key: str
    upload_url: str
    headers: dict[str, str]
    expires_in: int


def url_subida(actor: Actor, content_type: str, size_bytes: int) -> UrlSubida:
    ext = TIPOS.get(content_type)
    if ext is None:
        raise ValidacionError("Adjunte una foto (JPG, PNG, WEBP) o un PDF")
    s = get_settings()
    if size_bytes > s.max_upload_bytes:
        raise ValidacionError(f"El archivo supera el máximo de {s.max_upload_mb} MB")
    storage = get_storage()
    key = storage.portal_adjunto_key(actor.tenant_id, ext)
    return UrlSubida(
        key, storage.presign_put(key, content_type), {"Content-Type": content_type}, s.s3_presigned_ttl_seconds
    )


async def validar(actor: Actor, adjuntos: list[Adjunto]) -> list[dict[str, Any]]:
    salida = []
    for a in adjuntos:
        m = _CLAVE.fullmatch(a.key)
        if m is None or m.group("tenant") != str(actor.tenant_id):
            raise ValidacionError(f"El adjunto «{a.nombre}» no es válido: súbalo de nuevo")
        tamano = await run_in_threadpool(get_storage().object_size, a.key)
        if tamano is None:
            raise ValidacionError(f"El adjunto «{a.nombre}» aún no se ha subido")
        salida.append({"key": a.key, "nombre": a.nombre, "tipo": MIME[m.group("ext")], "tamano": tamano})
    return salida


def url_descarga(adjunto: dict[str, Any]) -> str:
    return get_storage().presign_get(
        adjunto["key"], adjunto.get("nombre") or "adjunto", adjunto.get("tipo") or "application/octet-stream"
    )
