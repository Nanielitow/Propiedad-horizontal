from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db import rls  # noqa: F401  (registra el listener after_begin)

settings = get_settings()

# API (async, asyncpg). Rol app_user => sujeto a RLS.
engine = create_async_engine(
    settings.database_url,
    pool_size=10,
    max_overflow=10,
    pool_pre_ping=True,
)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Workers de Celery (sync, psycopg). También app_user.
sync_engine = create_engine(settings.sync_database_url, pool_size=5, pool_pre_ping=True)
SyncSessionLocal = sessionmaker(sync_engine, class_=Session, expire_on_commit=False)
