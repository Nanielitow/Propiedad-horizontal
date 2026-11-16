from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context
from app.core.config import get_settings
from app.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Para `alembic revision --autogenerate`. Revisar SIEMPRE el resultado: RLS,
# triggers y funciones viven en SQL y autogenerate no los ve.
target_metadata = Base.metadata


def run_migrations_online() -> None:
    # Las migraciones corren con el OWNER del esquema, no con app_user.
    url = get_settings().migrations_database_url
    if not url:
        raise RuntimeError("MIGRATIONS_DATABASE_URL no está configurada")

    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            transaction_per_migration=True,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("Modo offline no soportado: ejecutar contra una base de datos")
run_migrations_online()
