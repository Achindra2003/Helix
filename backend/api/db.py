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
    from .conversation import models as conversation_models  # noqa: F401
    from .prompts import models as prompt_models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


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
