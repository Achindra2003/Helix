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

def _engine_kwargs() -> dict:
    """Engine options, adjusted for connection poolers that sit in front of PG.

    Supabase (and PgBouncer generally) offers a transaction-mode pooler on port
    6543. In that mode a client does not keep one server connection for the life
    of a session, which breaks asyncpg: it prepares statements under generated
    names and reuses them, and the next statement can land on a different server
    connection where that name was never prepared. The symptom is an
    intermittent `prepared statement "__asyncpg_stmt_N__" does not exist` under
    concurrency — it passes every local test and fails in production.

    Turning both caches off makes each statement self-contained, which is what
    the pooler requires. It costs a re-parse per statement; that is the price of
    the pooler, not a bug.

    Direct connections (port 5432) keep the caches. Run migrations there
    regardless: DDL through a transaction pooler is its own set of surprises.
    """
    kwargs: dict = {"echo": False, "future": True}
    if settings.database_url.startswith("postgresql+asyncpg") and settings.db_pooled:
        kwargs["connect_args"] = {"statement_cache_size": 0}
        kwargs["prepared_statement_cache_size"] = 0
    return kwargs


# Works on SQLite (dev) and Postgres (prod) alike.
engine = create_async_engine(settings.database_url, **_engine_kwargs())
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


async def connect() -> None:
    """Create tables on startup, unless the deployment runs migrations instead.

    Two postures, on purpose (see migrations/env.py):

    - **Self-hosters** keep this. `docker compose up` must be the whole install,
      and "now run alembic upgrade head" is a second step that turns a
      one-command install into a support question.
    - **The hosted instance** sets `db_auto_create=0` and runs
      `alembic upgrade head` as a deploy step, so schema changes are reviewed,
      ordered, and reversible rather than inferred at boot.

    The two agree: the baseline migration is verified to build the same schema
    this does.
    """
    # Import models so they register on Base.metadata before create_all. All
    # six modules, explicitly: a table that has not been imported is silently
    # absent. `telemetry` used to be missing here and `llm_calls` was created
    # only because api/main.py imports it first — true by accident, and it
    # would have broken the moment that import moved.
    from . import models  # noqa: F401
    from . import telemetry as telemetry_models  # noqa: F401
    from .conversation import embeddings as embedding_models  # noqa: F401
    from .conversation import models as conversation_models  # noqa: F401
    from .documents import models as document_models  # noqa: F401
    from .prompts import models as prompt_models  # noqa: F401

    if not settings.db_auto_create:
        return

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
