"""Cuentas reales: invitaciones, recuperación de clave, dueño de la plataforma y demo por copropiedad.

Revision ID: 0012
Revises: 0011
"""

from pathlib import Path

from alembic import op

revision = "0012"
down_revision = "0011"
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
    _run_sql_file("0012_cuentas.up.sql")


def downgrade() -> None:
    _run_sql_file("0012_cuentas.down.sql")
