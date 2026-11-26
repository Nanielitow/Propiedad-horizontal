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
from collections.abc import Iterator
from contextlib import contextmanager

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
    # Unidades, copropietarios y residentes (0007)
    "personas",
    "unidad_personas",
    "vehiculos",
    "importaciones_unidades",
    "auditoria_unidades",
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
    # Cartera de cuotas (0008)
    "cartera_config",
    "conceptos_cartera",
    "periodos_cartera",
    "cargos_cartera",
    "pagos_cartera",
    "aplicaciones_pago",
    "ajustes_cartera",
    "paz_y_salvos",
    "auditoria_cartera",
    # Portal del residente (0009)
    "pqrs",
    "pqrs_mensajes",
    "circulares",
    "circular_lecturas",
    "auditoria_portal",
    # Asambleas (0010)
    "asambleas",
    "asamblea_padron",
    "asamblea_asistencias",
    "asamblea_puntos",
    "asamblea_votos",
]
# Tablas con id IDENTITY cuya secuencia debe continuar tras restaurar
_IDENTITY_TABLES = [
    "audit_logs",
    "auditoria_recaudos",
    "auditoria_activos",
    "auditoria_unidades",
    "auditoria_cartera",
    "auditoria_portal",
]
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


@contextmanager
def sin_triggers(conn: Connection) -> Iterator[None]:
    """Apaga los triggers PROPIOS (consecutivos, estado inicial, auditoría, inmutabilidad) de las
    tablas de la demo mientras dura el bloque, dentro de la transacción de `conn`.

    Usa ALTER TABLE ... DISABLE TRIGGER USER, que basta con ser DUEÑO de la tabla: funciona en
    una base administrada (Neon), donde no somos superusuario y `session_replication_role` no se
    puede cambiar. Las llaves foráneas siguen validándose, así que se inserta en el orden de TABLES.
    Si algo falla, el rollback deja los triggers como estaban.
    """
    for table in map(_ident, TABLES):
        conn.execute(text(f"ALTER TABLE public.{table} DISABLE TRIGGER USER"))
    yield
    for table in map(_ident, TABLES):
        conn.execute(text(f"ALTER TABLE public.{table} ENABLE TRIGGER USER"))


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
        # La restauración vacía TODAS las tablas: jamás con copropiedades reales en la base
        reales = conn.scalar(text("SELECT count(*) FROM public.tenants WHERE NOT is_demo AND deleted_at IS NULL"))
        if reales:
            raise RuntimeError(
                f"Hay {reales} copropiedad(es) reales en esta base: restaurar la demo las borraría. Operación cancelada."
            )
        in_snapshot = set(
            conn.scalars(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema = :s"), {"s": SNAPSHOT_SCHEMA}
            )
        )
        # Los triggers no deben actuar al restaurar una foto ya consistente
        with sin_triggers(conn):
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
        # Todo lo que viene de la instantánea es de ejemplo (fotos anteriores a la migración 0012 no traen la marca)
        conn.execute(text("UPDATE public.tenants SET is_demo = true"))
        # Copropiedades restauradas desde una foto sin conceptos de recaudo: crearlos (idempotente)
        conn.execute(text("SELECT seed_conceptos_recaudo(id) FROM public.tenants"))
        conn.execute(text("SELECT seed_categorias_activos(id) FROM public.tenants"))
        conn.execute(text("SELECT seed_conceptos_cartera(id) FROM public.tenants"))
    log.info("demo restaurada: %s", counts)
    return counts


def restablecer_conjuntos_demo() -> dict[str, int]:
    """Deja como nuevos SOLO los conjuntos de demostración de la instantánea, sin tocar las copropiedades reales.

    A diferencia de restore_snapshot (que vacía todas las tablas), borra y vuelve a insertar únicamente las filas de
    los conjuntos de la instantánea (todas las tablas de la demo tienen tenant_id). Las cuentas demo se recrean si
    faltan; nunca se borran usuarios. Todo en una transacción: o queda completo o no se toca nada. Se niega si alguno
    de esos conjuntos fue marcado como real.
    """
    counts: dict[str, int] = {}
    with _owner_engine().begin() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM information_schema.schemata WHERE schema_name = :s"), {"s": SNAPSHOT_SCHEMA}
        ).first()
        if not exists:
            raise RuntimeError("No hay instantánea de la demo en esta base")
        ids = list(conn.scalars(text(f"SELECT id FROM {SNAPSHOT_SCHEMA}.tenants")))  # noqa: S608
        if not ids:
            raise RuntimeError("La instantánea de la demo no tiene conjuntos")
        reales = list(
            conn.scalars(text("SELECT name FROM public.tenants WHERE id = ANY(:ids) AND NOT is_demo"), {"ids": ids})
        )
        if reales:
            raise RuntimeError(f"Estos conjuntos ya no están marcados como demostración: {', '.join(reales)}")
        in_snapshot = set(
            conn.scalars(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema = :s"), {"s": SNAPSHOT_SCHEMA}
            )
        )
        with sin_triggers(conn):
            conn.execute(text("DELETE FROM public.account_tokens WHERE tenant_id = ANY(:ids)"), {"ids": ids})
            # Hijos primero (orden inverso de TABLES); las cuentas (users) nunca se borran
            for table in map(_ident, reversed(TABLES)):
                if table == "users":
                    continue
                col = "id" if table == "tenants" else "tenant_id"
                conn.execute(text(f"DELETE FROM public.{table} WHERE {col} = ANY(:ids)"), {"ids": ids})  # noqa: S608
            for table in map(_ident, TABLES):
                if table not in in_snapshot:
                    counts[table] = 0
                    continue
                cols = ", ".join(_columns(conn, SNAPSHOT_SCHEMA, table))
                filtro = (
                    ""
                    if table == "users"
                    else ("WHERE id = ANY(:ids)" if table == "tenants" else "WHERE tenant_id = ANY(:ids)")
                )
                # Las filas de estos conjuntos se acaban de borrar, así que no hay choques, salvo: cuentas demo que ya
                # existen (users) y ids numéricos de auditoría. (ON CONFLICT no admite restricciones diferibles,
                # por eso no va en las demás tablas.)
                conflicto = (
                    " ON CONFLICT DO NOTHING"
                    if table == "users"
                    else (" ON CONFLICT (id) DO NOTHING" if table in _IDENTITY_TABLES else "")
                )
                result = conn.execute(
                    text(
                        f"INSERT INTO public.{table} ({cols}) OVERRIDING SYSTEM VALUE "  # noqa: S608
                        f"SELECT {cols} FROM {SNAPSHOT_SCHEMA}.{table} {filtro}{conflicto}"
                    ),
                    {"ids": ids},
                )
                counts[table] = result.rowcount
        conn.execute(text("UPDATE public.tenants SET is_demo = true WHERE id = ANY(:ids)"), {"ids": ids})
        for table in map(_ident, _IDENTITY_TABLES):
            conn.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('public.{table}', 'id'), "  # noqa: S608
                    f"coalesce((SELECT max(id) FROM public.{table}), 0) + 1, false)"
                )
            )
        for semilla in ("seed_conceptos_recaudo", "seed_categorias_activos", "seed_conceptos_cartera"):
            conn.execute(text(f"SELECT {semilla}(id) FROM public.tenants WHERE id = ANY(:ids)"), {"ids": ids})  # noqa: S608
    log.info("conjuntos de demostración restablecidos: %s", {k: v for k, v in counts.items() if v})
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
