from collections.abc import AsyncIterator
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from .config import settings

# `future=True` async engine; works on SQLite (dev) and Postgres (prod) alike.
engine = create_async_engine(settings.database_url, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


async def connect() -> None:
    """Create tables on startup. Real migrations (Alembic) replace this later."""
    # Import models so they register on Base.metadata before create_all.
    from . import models  # noqa: F401
    from .conversation import embeddings as embedding_models  # noqa: F401
    from .conversation import models as conversation_models  # noqa: F401
    from .documents import models as document_models  # noqa: F401
    from .prompts import models as prompt_models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # create_all only creates missing *tables*; columns added to an
        # existing table (e.g. deep_runs.provenance) would silently not exist
        # on a dev DB created before them. This forward-only shim adds them.
        # Real migrations (Alembic) replace this for the hosted instance.
        await conn.run_sync(_add_missing_columns)


def _add_missing_columns(conn) -> None:
    from sqlalchemy import inspect as sa_inspect

    inspector = sa_inspect(conn)
    for table in Base.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        existing = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing:
                continue
            ddl = (
                f"ALTER TABLE {table.name} ADD COLUMN "
                f"{column.name} {column.type.compile(conn.dialect)}"
            )
            conn.execute(text(ddl))  # pre-existing rows read NULL — callers
            # treat provenance columns as optional (`row.model or ''`)


async def disconnect() -> None:
    await engine.dispose()


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request."""
    async with SessionLocal() as session:
        yield session


async def db_ping() -> str:
    """Prove the DB round-trips. Returns the current UTC time."""
    async with SessionLocal() as session:
        await session.execute(text("SELECT 1"))
    return datetime.now(timezone.utc).isoformat()
