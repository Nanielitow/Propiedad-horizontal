"""Pruebas del aislamiento multi-tenant y RBAC A NIVEL DE BASE DE DATOS.

Se conectan como app_user (el mismo rol que la API) y cada prueba corre dentro
de una transacción que se revierte al final: no dejan datos.
Requieren la base de datos de docker compose: npm run test (desde la raíz).
"""

import os
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError

pytestmark = pytest.mark.integration

ZERO_VECTOR = "[" + ",".join(["0.01"] * 1536) + "]"


@pytest.fixture
def conn() -> Iterator[Connection]:
    url = os.environ.get("SYNC_DATABASE_URL")
    if not url:
        pytest.skip("SYNC_DATABASE_URL no configurada")
    engine = create_engine(url)
    with engine.connect() as connection:
        tx = connection.begin()
        try:
            yield connection
        finally:
            tx.rollback()
    engine.dispose()


def as_(conn: Connection, tenant: uuid.UUID | None, role: str) -> None:
    conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant) if tenant else ""})
    conn.execute(text("SELECT set_config('app.role', :r, true)"), {"r": role})


def insert_doc(conn: Connection, tenant: uuid.UUID, access: str, content: str) -> uuid.UUID:
    doc_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO documents (id, tenant_id, title, original_filename, category, access_level,"
            " status, storage_key, size_bytes, sha256)"
            " VALUES (:id, :t, :title, 'x.pdf', 'CONVIVENCIA', CAST(:a AS access_level), 'READY', 'k', 10, :sha)"
        ),
        {"id": doc_id, "t": tenant, "title": f"doc {access}", "a": access, "sha": uuid.uuid4().hex * 2},
    )
    conn.execute(
        text(
            "INSERT INTO document_chunks (tenant_id, document_id, chunk_index, page_number, page_end,"
            " category, access_level, content, token_count, embedding, embedding_model)"
            " VALUES (:t, :d, 0, 1, 1, 'CONVIVENCIA', CAST(:a AS access_level), :c, 5, CAST(:e AS vector), 'test')"
        ),
        {"t": tenant, "d": doc_id, "a": access, "c": content, "e": ZERO_VECTOR},
    )
    return doc_id


@pytest.fixture
def world(conn: Connection) -> dict[str, uuid.UUID]:
    """Dos edificios, cada uno con un documento PUBLIC y uno ADMIN."""
    ids: dict[str, uuid.UUID] = {}
    for name in ("a", "b"):
        tenant = uuid.uuid4()
        conn.execute(
            text("INSERT INTO tenants (id, name, slug) VALUES (:id, :n, :s)"),
            {"id": tenant, "n": f"Edificio {name}", "s": f"test-{tenant}"},
        )
        as_(conn, tenant, "SYSTEM")
        ids[name] = tenant
        ids[f"{name}_public"] = insert_doc(conn, tenant, "PUBLIC", f"horario de la piscina edificio {name}")
        ids[f"{name}_admin"] = insert_doc(conn, tenant, "ADMIN", f"contrato de vigilancia edificio {name}")
    return ids


def visible_docs(conn: Connection) -> set[uuid.UUID]:
    return set(conn.scalars(text("SELECT id FROM documents")))


def test_sin_contexto_no_se_ve_nada(conn: Connection, world: dict[str, uuid.UUID]) -> None:
    as_(conn, None, "")
    assert visible_docs(conn) == set()
    assert conn.scalar(text("SELECT count(*) FROM document_chunks")) == 0


def test_residente_solo_ve_publicos_de_su_edificio(conn: Connection, world: dict[str, uuid.UUID]) -> None:
    as_(conn, world["a"], "RESIDENTE")
    assert visible_docs(conn) == {world["a_public"]}
    assert set(conn.scalars(text("SELECT access_level::text FROM document_chunks"))) == {"PUBLIC"}


def test_admin_ve_todo_su_edificio_y_nada_del_otro(conn: Connection, world: dict[str, uuid.UUID]) -> None:
    as_(conn, world["a"], "ADMIN")
    assert visible_docs(conn) == {world["a_public"], world["a_admin"]}


def test_no_se_puede_escribir_en_otro_edificio(conn: Connection, world: dict[str, uuid.UUID]) -> None:
    as_(conn, world["a"], "ADMIN")
    with pytest.raises(DBAPIError, match="row-level security"), conn.begin_nested():
        insert_doc(conn, world["b"], "PUBLIC", "intento de escritura cruzada")


def test_residente_no_puede_crear_documentos(conn: Connection, world: dict[str, uuid.UUID]) -> None:
    as_(conn, world["a"], "RESIDENTE")
    with pytest.raises(DBAPIError, match="row-level security"), conn.begin_nested():
        insert_doc(conn, world["a"], "PUBLIC", "residente intentando subir")


def test_fk_compuesta_impide_chunk_apuntando_a_documento_de_otro_edificio(
    conn: Connection, world: dict[str, uuid.UUID]
) -> None:
    as_(conn, world["a"], "SYSTEM")
    with pytest.raises(IntegrityError, match="foreign key"), conn.begin_nested():
        conn.execute(
            text(
                "INSERT INTO document_chunks (tenant_id, document_id, chunk_index, page_number, page_end,"
                " category, access_level, content, token_count, embedding, embedding_model)"
                " VALUES (:t, :d, 9, 1, 1, 'CONVIVENCIA', 'PUBLIC', 'x', 1, CAST(:e AS vector), 'test')"
            ),
            {"t": world["a"], "d": world["b_public"], "e": ZERO_VECTOR},
        )


def test_reclasificar_documento_propaga_a_sus_chunks(conn: Connection, world: dict[str, uuid.UUID]) -> None:
    as_(conn, world["a"], "ADMIN")
    conn.execute(text("UPDATE documents SET access_level = 'PUBLIC' WHERE id = :d"), {"d": world["a_admin"]})
    as_(conn, world["a"], "RESIDENTE")
    assert world["a_admin"] in visible_docs(conn)
    assert (
        conn.scalar(text("SELECT count(*) FROM document_chunks WHERE document_id = :d"), {"d": world["a_admin"]}) == 1
    )


def test_hybrid_search_no_cruza_edificios_aunque_se_le_pida(conn: Connection, world: dict[str, uuid.UUID]) -> None:
    """Defensa en profundidad: aunque la API tuviera un bug y pasara el tenant B
    como parámetro, RLS (contexto = tenant A) impide devolver datos de B."""
    as_(conn, world["a"], "ADMIN")
    rows = conn.execute(
        text("SELECT * FROM hybrid_search(:t, true, CAST(:e AS vector), 'piscina', 10)"),
        {"t": world["b"], "e": ZERO_VECTOR},
    ).all()
    assert rows == []

    rows = conn.execute(
        text("SELECT document_id FROM hybrid_search(:t, false, CAST(:e AS vector), 'piscina', 10)"),
        {"t": world["a"], "e": ZERO_VECTOR},
    ).all()
    assert {r.document_id for r in rows} == {world["a_public"]}


def test_auditoria_es_append_only(conn: Connection, world: dict[str, uuid.UUID]) -> None:
    as_(conn, world["a"], "RESIDENTE")
    conn.execute(text("INSERT INTO audit_logs (tenant_id, action) VALUES (:t, 'document.view')"), {"t": world["a"]})
    assert conn.scalar(text("SELECT count(*) FROM audit_logs")) == 0  # residente no lee
    as_(conn, world["a"], "ADMIN")
    assert conn.scalar(text("SELECT count(*) FROM audit_logs")) == 1
    deleted = conn.execute(text("DELETE FROM audit_logs")).rowcount
    assert deleted == 0  # ni el admin puede borrar


def test_residente_no_puede_usar_returning_en_auditoria(conn: Connection, world: dict[str, uuid.UUID]) -> None:
    """Regresión: INSERT ... RETURNING aplica las políticas de SELECT a la fila
    devuelta. El ORM lo usa con db.add(), así que la API debe insertar la
    auditoría con un INSERT simple (ver documents.file_url)."""
    as_(conn, world["a"], "RESIDENTE")
    with pytest.raises(DBAPIError, match="row-level security"), conn.begin_nested():
        conn.execute(
            text("INSERT INTO audit_logs (tenant_id, action) VALUES (:t, 'document.view') RETURNING id"),
            {"t": world["a"]},
        )
