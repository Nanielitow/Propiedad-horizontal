"""hybrid_search v2: léxico con OR, distancia semántica, filtro por modelo de embeddings.

Revision ID: 0002
Revises: 0001
"""

from pathlib import Path

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def _run_sql_file(name: str) -> None:
    sql = (SQL_DIR / name).read_text(encoding="utf-8")
    with op.get_bind().connection.dbapi_connection.cursor() as cur:
        cur.execute(sql)


def upgrade() -> None:
    _run_sql_file("0002_hybrid_search_v2.up.sql")


def downgrade() -> None:
    _run_sql_file("0002_hybrid_search_v2.down.sql")
