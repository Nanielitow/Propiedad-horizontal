"""Demo pública: instantánea y restauración nocturna de los datos.

Flujo:
  1. Se cargan los documentos de demostración y se procesan (ingesta, OCR,
     vencimientos, actas, comparación de cotizaciones): app.scripts.demo load
  2. Se guarda una instantánea de TODAS las tablas en el esquema demo_snapshot:
     app.scripts.demo snapshot
  3. Cada noche (Celery beat) se restaura esa instantánea en una sola
     transacción y se borran de R2 los archivos que subieron los visitantes.

Restaurar desde SQL (y no re-procesando los documentos) hace que el reinicio
sea instantáneo y no gaste llamadas a la IA.

Usa la conexión del DUEÑO del esquema (MIGRATIONS_DATABASE_URL): necesita
TRUNCATE sobre todas las tablas y no debe estar limitada por RLS.
"""

import logging
import re

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

from app.core.config import get_settings
from app.services.storage.s3 import get_storage

log = logging.getLogger(__name__)

SNAPSHOT_SCHEMA = "demo_snapshot"
# Orden padres -> hijos (las claves foráneas exigen insertar en este orden)
TABLES = [
    "tenants",
    "users",
    "units",
    "memberships",
    "documents",
    "document_pages",
    "document_chunks",
    "processing_jobs",
    "deadlines",
    "deadline_notifications",
    "quote_comparisons",
    "quote_comparison_documents",
    "minutes_summaries",
    "action_items",
    "conversations",
    "messages",
    "audit_logs",
    # Recaudos (0003)
    "secuencias",
    "conceptos_recaudo",
    "zonas_sociales",
    "reservas",
    "cierres_caja",
    "entregas_internas",
    "recaudos",
    "recaudo_items",
    "recaudo_parqueadero",
    "consignaciones",
    "consignacion_recaudos",
    "auditoria_recaudos",
    "alertas_recaudo",
    "cortes_mensuales",
    # Activos y mantenimiento (0005)
    "categorias_activos",
    "contratistas",
    "activos",
    "activo_documentos",
    "evidencias",
    "lecturas_uso",
    "planes_preventivos",
    "actividades_programadas",
    "reprogramaciones",
    "novedades",
    "mantenimientos_ejecutados",
    "recomendaciones_tecnicas",
    "auditoria_activos",
    "notificaciones_mantenimiento",
]
# Tablas con id IDENTITY cuya secuencia debe continuar tras restaurar
_IDENTITY_TABLES = ["audit_logs", "auditoria_recaudos", "auditoria_activos"]
_KEY = re.compile(r"^tenants/[0-9a-f-]{36}/documents/(?P<doc>[0-9a-f-]{36})/")
_SOPORTE = re.compile(r"^tenants/[0-9a-f-]{36}/recaudos/soportes/")


def _owner_engine():  # type: ignore[no-untyped-def]
    url = get_settings().migrations_database_url
    if not url:
        raise RuntimeError("MIGRATIONS_DATABASE_URL no está configurada")
    return create_engine(url)


# Los identificadores (tablas, columnas) no admiten parámetros en SQL, así que se
# interpolan. Es seguro porque NUNCA vienen del usuario: las tablas salen de la
# constante TABLES y las columnas del catálogo de Postgres. Además se valida su
# forma antes de usarlos (defensa en profundidad), de ahí los `noqa: S608`.
_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


def _ident(name: str) -> str:
    if not _IDENT.match(name):
        raise ValueError(f"Identificador SQL inesperado: {name!r}")
    return name


def _columns(conn: Connection, schema: str, table: str) -> list[str]:
    # Se excluyen las columnas generadas (p. ej. content_tsv): Postgres las calcula
    rows = conn.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = :s AND table_name = :t AND is_generated = 'NEVER' ORDER BY ordinal_position"
        ),
        {"s": schema, "t": table},
    )
    return [f'"{_ident(r[0])}"' for r in rows]


def save_snapshot() -> dict[str, int]:
    counts: dict[str, int] = {}
    with _owner_engine().begin() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SNAPSHOT_SCHEMA} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {SNAPSHOT_SCHEMA}"))
        for table in map(_ident, TABLES):
            cols = ", ".join(_columns(conn, "public", table))
            conn.execute(text(f"CREATE TABLE {SNAPSHOT_SCHEMA}.{table} AS SELECT {cols} FROM public.{table}"))  # noqa: S608
            counts[table] = conn.execute(text(f"SELECT count(*) FROM {SNAPSHOT_SCHEMA}.{table}")).scalar_one()  # noqa: S608
    log.info("instantánea de la demo guardada: %s", counts)
    return counts


def restore_snapshot() -> dict[str, int]:
    """Restaura todo en UNA transacción: o queda la demo completa o no se toca nada."""
    counts: dict[str, int] = {}
    with _owner_engine().begin() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM information_schema.schemata WHERE schema_name = :s"), {"s": SNAPSHOT_SCHEMA}
        ).first()
        if not exists:
            raise RuntimeError("No hay instantánea de la demo: ejecute primero `python -m app.scripts.demo snapshot`")
        in_snapshot = set(
            conn.scalars(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema = :s"), {"s": SNAPSHOT_SCHEMA}
            )
        )
        # Los triggers (consecutivos, estado inicial, auditoría, inmutabilidad) no deben
        # actuar al restaurar una foto ya consistente. Requiere superusuario (el dueño lo es).
        conn.execute(text("SET LOCAL session_replication_role = replica"))
        conn.execute(text("TRUNCATE " + ", ".join(f"public.{t}" for t in TABLES) + " RESTART IDENTITY CASCADE"))
        for table in map(_ident, TABLES):
            if table not in in_snapshot:  # instantánea anterior a una migración: la tabla queda vacía
                counts[table] = 0
                continue
            cols = ", ".join(_columns(conn, SNAPSHOT_SCHEMA, table))
            result = conn.execute(
                text(
                    f"INSERT INTO public.{table} ({cols}) OVERRIDING SYSTEM VALUE "  # noqa: S608
                    f"SELECT {cols} FROM {SNAPSHOT_SCHEMA}.{table}"
                )
            )
            counts[table] = result.rowcount
        # Las secuencias de ids de auditoría deben continuar después del máximo restaurado
        for table in map(_ident, _IDENTITY_TABLES):
            conn.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('public.{table}', 'id'), "  # noqa: S608
                    f"coalesce((SELECT max(id) FROM public.{table}), 0) + 1, false)"
                )
            )
        # Copropiedades restauradas desde una foto sin conceptos de recaudo: crearlos (idempotente)
        conn.execute(text("SELECT seed_conceptos_recaudo(id) FROM public.tenants"))
        conn.execute(text("SELECT seed_categorias_activos(id) FROM public.tenants"))
    log.info("demo restaurada: %s", counts)
    return counts


def delete_orphan_files() -> int:
    """Borra del almacenamiento los PDF de documentos que ya no existen en la base
    (los que subieron los visitantes durante el día)."""
    with _owner_engine().connect() as conn:
        alive = {str(r[0]) for r in conn.execute(text("SELECT id FROM public.documents"))}
        soportes = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT soporte_key FROM public.recaudos WHERE soporte_key IS NOT NULL UNION "
                    "SELECT soporte_bancario_key FROM public.consignaciones WHERE soporte_bancario_key IS NOT NULL"
                )
            )
        }
    storage = get_storage()
    orphans = [
        key
        for key in storage.list_keys("tenants/")
        if ((m := _KEY.match(key)) and m.group("doc") not in alive) or (_SOPORTE.match(key) and key not in soportes)
    ]
    if orphans:
        storage.delete_many(orphans)
    log.info("archivos huérfanos eliminados: %s", len(orphans))
    return len(orphans)
