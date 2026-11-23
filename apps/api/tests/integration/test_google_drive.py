"""Importación desde Google Drive: descarga con el token del usuario, validación,
duplicados e ingesta. Google se simula con un transporte falso de httpx."""

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import select

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.security import create_access_token
from app.main import app
from app.models import Document
from app.models.enums import UserRole
from app.services import google_drive
from app.workers.celery_app import celery_app
from tests.integration.conftest import Mundo

pytestmark = pytest.mark.integration

PDF = b"%PDF-1.7\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF"
TOKEN = "ya29.token-de-prueba-que-no-se-guarda"
# id -> (metadatos de Drive, contenido o código de error)
ARCHIVOS: dict[str, tuple[dict[str, Any], bytes | int]] = {
    "pdf_reglamento_01": (
        {
            "id": "pdf_reglamento_01",
            "name": "Reglamento.pdf",
            "mimeType": "application/pdf",
            "size": str(len(PDF)),
            "webViewLink": "https://drive.google.com/file/d/pdf_reglamento_01/view",
        },
        PDF,
    ),
    "gdoc_circular_0001": (
        {
            "id": "gdoc_circular_0001",
            "name": "Circular de diciembre",
            "mimeType": "application/vnd.google-apps.document",
            "webViewLink": "https://docs.google.com/document/d/gdoc_circular_0001",
        },
        PDF + b"exportado",
    ),
    "imagen_fachada_01": (
        {"id": "imagen_fachada_01", "name": "fachada.jpg", "mimeType": "image/jpeg", "size": "9"},
        b"\xff\xd8",
    ),
    "pdf_falso_000001": (
        {"id": "pdf_falso_000001", "name": "falso.pdf", "mimeType": "application/pdf", "size": "5"},
        b"<html",
    ),
    "sin_permiso_0001": ({}, 404),
}


def _google(request: httpx.Request) -> httpx.Response:
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"  # el token del usuario, tal cual
    partes = request.url.path.split("/")  # /drive/v3/files/{id}[/export]
    file_id = partes[4]
    meta, contenido = ARCHIVOS.get(file_id, ({}, 404))
    if isinstance(contenido, int):
        return httpx.Response(contenido, json={"error": {"errors": [{"reason": "notFound"}]}})
    if partes[-1] == "export":
        assert request.url.params["mimeType"] == "application/pdf"
        return httpx.Response(200, content=contenido)
    if request.url.params.get("alt") == "media":
        return httpx.Response(200, content=contenido)
    return httpx.Response(200, json=meta)


class AlmacenFalso:
    def __init__(self) -> None:
        self.archivos: dict[str, bytes] = {}

    def document_key(self, tenant_id: Any, document_id: Any, name: str) -> str:
        return f"tenants/{tenant_id}/documents/{document_id}/{name}"

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        self.archivos[key] = data

    def delete(self, key: str) -> None:
        self.archivos.pop(key, None)


@pytest.fixture
async def http(
    mundo: Mundo, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[httpx.AsyncClient, Mundo, AlmacenFalso, list[Any]]]:
    almacen = AlmacenFalso()
    encoladas: list[Any] = []

    class Resultado:
        id = "tarea-falsa"

    monkeypatch.setattr("app.api.v1.documents.get_storage", lambda: almacen)
    monkeypatch.setattr(
        google_drive, "nuevo_cliente", lambda: httpx.AsyncClient(transport=httpx.MockTransport(_google))
    )
    monkeypatch.setattr(
        celery_app, "send_task", lambda nombre, args=None, **_: encoladas.append((nombre, args)) or Resultado()
    )

    async def _db() -> AsyncIterator[Any]:
        yield mundo.db

    app.dependency_overrides[get_db] = _db
    app.state.redis = Redis.from_url(get_settings().redis_url)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as cliente:
            yield cliente, mundo, almacen, encoladas
    finally:
        app.dependency_overrides.clear()
        await app.state.redis.aclose()


async def _importar(cliente: httpx.AsyncClient, mundo: Mundo, quien: str, *ids: str) -> httpx.Response:
    token, _ = create_access_token(mundo.usuarios[quien])
    return await cliente.post(
        f"/api/v1/tenants/{mundo.tenant}/documents/import/google-drive",
        json={"access_token": TOKEN, "files": [{"id": i} for i in ids], "category": "CONVIVENCIA"},
        headers={"Authorization": f"Bearer {token}"},
    )


async def test_importa_pdf_y_google_doc_y_rechaza_lo_demas(http: tuple) -> None:
    cliente, mundo, almacen, encoladas = http
    r = await _importar(
        cliente,
        mundo,
        "ADMIN",
        "pdf_reglamento_01",
        "gdoc_circular_0001",
        "imagen_fachada_01",
        "pdf_falso_000001",
        "sin_permiso_0001",
    )
    assert r.status_code == 200, r.text
    estados = {x["file_id"]: (x["estado"], x["mensaje"]) for x in r.json()["resultados"]}
    assert estados["pdf_reglamento_01"] == ("IMPORTADO", None)
    assert estados["gdoc_circular_0001"] == ("IMPORTADO", None)
    assert estados["imagen_fachada_01"][0] == "ERROR" and "Solo se pueden importar" in estados["imagen_fachada_01"][1]
    assert estados["pdf_falso_000001"] == ("ERROR", "El archivo descargado no es un PDF válido")
    assert estados["sin_permiso_0001"][0] == "ERROR" and "permiso" in estados["sin_permiso_0001"][1]

    await mundo.como(UserRole.ADMIN)
    docs = {d.source_ref: d for d in await mundo.db.scalars(select(Document).where(Document.source == "GOOGLE_DRIVE"))}
    assert set(docs) == {"pdf_reglamento_01", "gdoc_circular_0001"}
    circular = docs["gdoc_circular_0001"]
    assert (circular.original_filename, circular.title) == ("Circular de diciembre.pdf", "Circular de diciembre")
    assert circular.source_url == "https://docs.google.com/document/d/gdoc_circular_0001"
    assert circular.access_level.value == "PUBLIC"  # Convivencia es pública por defecto
    assert almacen.archivos[circular.storage_key].startswith(b"%PDF")
    assert len(encoladas) == 2  # ambos entran a la ingesta normal
    assert TOKEN not in str(encoladas)  # el token NUNCA viaja a la cola de tareas


async def test_no_importa_dos_veces_el_mismo_archivo(http: tuple) -> None:
    cliente, mundo, _, encoladas = http
    await _importar(cliente, mundo, "ADMIN", "pdf_reglamento_01")
    r = await _importar(cliente, mundo, "ADMIN", "pdf_reglamento_01")
    [resultado] = r.json()["resultados"]
    assert (resultado["estado"], resultado["mensaje"]) == ("DUPLICADO", "Ya se había importado")
    assert len(encoladas) == 1


async def test_solo_la_administracion_importa(http: tuple) -> None:
    cliente, mundo, _, _ = http
    assert (await _importar(cliente, mundo, "AUXILIAR", "pdf_reglamento_01")).status_code == 403
