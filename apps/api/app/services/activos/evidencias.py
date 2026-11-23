"""Evidencias: fotos de antes y después, fallas, el activo, informes y facturas escaneadas.

Se suben directo al almacenamiento con una URL firmada (como los soportes de
recaudos) y luego se registran: la API comprueba que el archivo exista, que esté
en la carpeta de la copropiedad y que la entidad (activo, mantenimiento o
novedad) también le pertenezca. Las evidencias no se editan ni se borran.
"""

import re
import uuid
from dataclasses import dataclass

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Activo, Evidencia, MantenimientoEjecutado, Novedad
from app.models.enums import EntidadEvidencia
from app.schemas.activos import EvidenciaIn
from app.services.activos.dominio import PUEDE_SUBIR_FOTOS, PUEDE_VER
from app.services.comun import Actor, NoEncontrado, ValidacionError, exigir
from app.services.storage.s3 import get_storage

TIPOS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "application/pdf": "pdf"}
MIME_POR_EXTENSION = {v: k for k, v in TIPOS.items()}
_CLAVE = re.compile(r"^tenants/(?P<tenant>[0-9a-f-]{36})/activos/evidencias/[0-9a-f-]{36}\.(?P<ext>jpg|png|webp|pdf)$")
_MODELO = {
    EntidadEvidencia.ACTIVO: Activo,
    EntidadEvidencia.MANTENIMIENTO: MantenimientoEjecutado,
    EntidadEvidencia.NOVEDAD: Novedad,
}


@dataclass(frozen=True)
class UrlSubida:
    storage_key: str
    upload_url: str
    headers: dict[str, str]
    expires_in: int


def url_subida(actor: Actor, content_type: str, size_bytes: int) -> UrlSubida:
    exigir(actor, PUEDE_SUBIR_FOTOS, "subir evidencias")
    extension = TIPOS.get(content_type)
    if extension is None:
        raise ValidacionError("La evidencia debe ser una foto (JPG, PNG, WEBP) o un PDF")
    settings = get_settings()
    if size_bytes > settings.max_upload_bytes:
        raise ValidacionError(f"El archivo supera el máximo de {settings.max_upload_mb} MB")
    storage = get_storage()
    key = storage.activo_evidencia_key(actor.tenant_id, extension)
    return UrlSubida(
        key, storage.presign_put(key, content_type), {"Content-Type": content_type}, settings.s3_presigned_ttl_seconds
    )


async def registrar(db: AsyncSession, actor: Actor, data: EvidenciaIn) -> Evidencia:
    exigir(actor, PUEDE_SUBIR_FOTOS, "subir evidencias")
    m = _CLAVE.fullmatch(data.storage_key)
    if m is None or m.group("tenant") != str(actor.tenant_id):
        raise ValidacionError("El archivo no es válido: súbalo de nuevo")
    entidad = await db.get(_MODELO[data.entidad], data.entidad_id)
    if entidad is None or entidad.tenant_id != actor.tenant_id:
        raise NoEncontrado("El registro al que pertenece la evidencia no existe")
    tamano = await run_in_threadpool(get_storage().object_size, data.storage_key)
    if tamano is None:
        raise ValidacionError("El archivo aún no se ha subido")
    if tamano > get_settings().max_upload_bytes:
        await run_in_threadpool(get_storage().delete, data.storage_key)
        raise ValidacionError("El archivo supera el tamaño máximo")
    ev = Evidencia(
        id=uuid.uuid4(),
        tenant_id=actor.tenant_id,
        entidad=data.entidad,
        entidad_id=data.entidad_id,
        momento=data.momento,
        storage_key=data.storage_key,
        content_type=MIME_POR_EXTENSION[m.group("ext")],
        size_bytes=tamano,
        descripcion=data.descripcion,
        subido_por_id=actor.user_id,
    )
    db.add(ev)
    await db.flush()
    return ev


async def listar(
    db: AsyncSession, actor: Actor, entidad: EntidadEvidencia, entidad_id: uuid.UUID
) -> list[tuple[Evidencia, str]]:
    """Evidencias de un registro con una URL firmada (5 minutos) para verlas."""
    exigir(actor, PUEDE_VER, "consultar evidencias")
    filas = await db.scalars(
        select(Evidencia)
        .where(Evidencia.entidad == entidad, Evidencia.entidad_id == entidad_id)
        .order_by(Evidencia.created_at)
    )
    storage = get_storage()
    return [
        (
            e,
            storage.presign_get(
                e.storage_key, f"evidencia-{e.momento.value.lower()}.{e.storage_key.rsplit('.', 1)[-1]}", e.content_type
            ),
        )
        for e in filas
    ]
