"""The forward-only column shim: a dev DB created before a column existed
gets it added at startup (create_all alone only creates missing *tables*)."""
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

import api.conversation.models  # noqa: F401 — register deep_runs on Base.metadata
from api.db import Base, _add_missing_columns


@pytest.mark.asyncio
async def test_missing_column_is_added_on_connect(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/old.db")
    async with engine.begin() as conn:
        # A deep_runs table from *before* the provenance columns existed.
        await conn.execute(
            text(
                "CREATE TABLE deep_runs ("
                "id VARCHAR PRIMARY KEY, workspace_id VARCHAR, "
                "conversation_id VARCHAR, branch_id VARCHAR, author_id VARCHAR, "
                "question TEXT, answer TEXT, status VARCHAR, stop_reason VARCHAR, "
                "depth INTEGER, stability FLOAT, confidence FLOAT, "
                "tokens_used INTEGER, duration_ms INTEGER, trace TEXT, "
                "created_at DATETIME)"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO deep_runs (id, workspace_id, conversation_id, "
                "branch_id, author_id, question, status) "
                "VALUES ('r1', 'w', 'c', 'b', 'u', 'q', 'done')"
            )
        )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)

    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text("SELECT model, provenance FROM deep_runs WHERE id='r1'")
            )
        ).first()
    # Old rows read NULL in the new columns — callers treat them as optional.
    assert row == (None, None)
    await engine.dispose()
