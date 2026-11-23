"""Módulo de recaudos y control de ingresos (docs/RECAUDOS.md).

Revision ID: 0003
Revises: 0002
"""

from pathlib import Path

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def _run_sql_file(name: str) -> None:
    sql = (SQL_DIR / name).read_text(encoding="utf-8")
    # Se usa el cursor DBAPI directamente: sin parámetros, psycopg ejecuta el
    # script completo (varias sentencias, bloques DO $$ ... $$, '%I' en format())
    # sin intentar interpretar ':' o '%' como placeholders.
    dbapi_conn = op.get_bind().connection.dbapi_connection
    with dbapi_conn.cursor() as cur:
        cur.execute(sql)


def upgrade() -> None:
    _run_sql_file("0003_recaudos.up.sql")


def downgrade() -> None:
    _run_sql_file("0003_recaudos.down.sql")
