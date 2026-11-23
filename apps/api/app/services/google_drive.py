"""Descarga de archivos de Google Drive con el permiso del propio usuario.

El navegador obtiene un token de acceso de Google con el alcance `drive.file`
(solo los archivos que el usuario ELIGE en el selector de Google) y lo envía
junto con los ids elegidos. Aquí se usa ese token una única vez para descargar:
nunca se guarda, ni se registra, ni viaja a la cola de tareas.

Los Google Docs se exportan a PDF; los PDF se descargan tal cual. Cualquier
otro tipo se rechaza.
"""

from dataclasses import dataclass

import httpx

API = "https://www.googleapis.com/drive/v3/files"
PDF = "application/pdf"
# Documentos nativos de Google que Drive puede exportar a PDF
EXPORTABLES = {
    "application/vnd.google-apps.document": "Documento de Google",
    "application/vnd.google-apps.presentation": "Presentación de Google",
    "application/vnd.google-apps.spreadsheet": "Hoja de cálculo de Google",
}
_CAMPOS = "id,name,mimeType,size,webViewLink,trashed"


class DriveError(Exception):
    """Error con mensaje apto para mostrar al usuario."""


@dataclass(frozen=True)
class ArchivoDrive:
    id: str
    nombre: str  # siempre termina en .pdf
    mime_original: str
    url: str | None
    contenido: bytes


def nuevo_cliente() -> httpx.AsyncClient:
    """Punto único de creación del cliente (los tests lo sustituyen por uno simulado)."""
    return httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0), follow_redirects=True)


def _error(resp: httpx.Response, accion: str) -> DriveError:
    if resp.status_code == 401:
        return DriveError("El permiso de Google expiró: vuelva a abrir el selector de Drive")
    if resp.status_code == 404:
        return DriveError("No se encontró el archivo o la app no tiene permiso sobre él")
    if resp.status_code == 403:
        motivo = ""
        try:
            motivo = resp.json()["error"]["errors"][0]["reason"]
        except (ValueError, KeyError, IndexError, TypeError):
            pass
        if motivo == "exportSizeLimitExceeded":
            return DriveError("Google no permite exportar documentos tan grandes: descárguelo como PDF y súbalo")
        if motivo in ("rateLimitExceeded", "userRateLimitExceeded"):
            return DriveError("Google limitó las descargas por un momento: intente de nuevo en un minuto")
        return DriveError("Google Drive no permitió descargar el archivo")
    return DriveError(f"Google Drive respondió con un error al {accion} (HTTP {resp.status_code})")


async def _leer_con_limite(
    cliente: httpx.AsyncClient, url: str, params: dict[str, str], token: str, max_bytes: int
) -> bytes:
    """Descarga por partes y corta en cuanto se pasa del máximo (no se confía en el tamaño declarado)."""
    partes: list[bytes] = []
    total = 0
    async with cliente.stream("GET", url, params=params, headers={"Authorization": f"Bearer {token}"}) as resp:
        if resp.status_code != 200:
            await resp.aread()
            raise _error(resp, "descargar")
        async for bloque in resp.aiter_bytes():
            total += len(bloque)
            if total > max_bytes:
                raise DriveError(f"El archivo supera el máximo de {max_bytes // (1024 * 1024)} MB")
            partes.append(bloque)
    return b"".join(partes)


async def descargar(cliente: httpx.AsyncClient, token: str, file_id: str, max_bytes: int) -> ArchivoDrive:
    meta = await cliente.get(
        f"{API}/{file_id}",
        params={"fields": _CAMPOS, "supportsAllDrives": "true"},
        headers={"Authorization": f"Bearer {token}"},
    )
    if meta.status_code != 200:
        raise _error(meta, "consultar el archivo")
    datos = meta.json()
    if datos.get("trashed"):
        raise DriveError("El archivo está en la papelera de Drive")
    mime = datos.get("mimeType", "")
    nombre = str(datos.get("name") or file_id).strip()

    if mime == PDF:
        if int(datos.get("size") or 0) > max_bytes:
            raise DriveError(f"El archivo supera el máximo de {max_bytes // (1024 * 1024)} MB")
        contenido = await _leer_con_limite(
            cliente, f"{API}/{file_id}", {"alt": "media", "supportsAllDrives": "true"}, token, max_bytes
        )
    elif mime in EXPORTABLES:
        contenido = await _leer_con_limite(cliente, f"{API}/{file_id}/export", {"mimeType": PDF}, token, max_bytes)
    else:
        raise DriveError("Solo se pueden importar PDF y documentos de Google (Docs, Presentaciones, Hojas)")

    if not contenido.startswith(b"%PDF-"):
        raise DriveError("El archivo descargado no es un PDF válido")
    if not nombre.lower().endswith(".pdf"):
        nombre = f"{nombre}.pdf"
    return ArchivoDrive(
        id=file_id, nombre=nombre, mime_original=mime, url=datos.get("webViewLink"), contenido=contenido
    )
