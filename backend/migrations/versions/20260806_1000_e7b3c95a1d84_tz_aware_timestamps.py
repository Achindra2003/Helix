"""timestamps carry their timezone

Every timestamp this product writes is tz-aware UTC (`models._now()`), but only
six columns — the ones in `api/models.py`, which spelled `DateTime(timezone=True)`
out — said so in the schema. The other thirteen were declared as bare
`Mapped[datetime]`, which SQLAlchemy resolves to `TIMESTAMP WITHOUT TIME ZONE`.

SQLite stores both as text and never complained, so the whole test suite passed
against a schema Postgres rejects: asyncpg refuses an aware value into a naive
column, and creating a conversation, saving a prompt, embedding a node and
recording an LLM call each returned 500. The declaration is fixed at the
declarative base (`api/db.py`); this brings existing databases along.

`USING ... AT TIME ZONE 'UTC'` is the part that matters for data already on
disk. Postgres would otherwise reinterpret those naive values in the session's
timezone, silently shifting every historical timestamp by the server's offset.
The values were written as UTC, so they are read back as UTC.

SQLite is skipped: the type is a no-op there, and rewriting thirteen columns
through batch mode (which recreates each table) would be real risk for no
change at all.

Revision ID: e7b3c95a1d84
Revises: d4a2b8c16f30
Create Date: 2026-08-06 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e7b3c95a1d84'
down_revision: Union[str, None] = 'd4a2b8c16f30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# The thirteen that were declared without a timezone. Kept as a literal list
# rather than derived from the metadata: a migration describes the schema at
# one moment in history, and must not change meaning when the models do.
_COLUMNS: list[tuple[str, str]] = [
    ("conversations", "created_at"),
    ("conversations", "concluded_at"),
    ("branches", "created_at"),
    ("branches", "resolved_at"),
    ("conversation_references", "created_at"),
    ("nodes", "created_at"),
    ("node_embeddings", "created_at"),
    ("deep_runs", "created_at"),
    ("resumable_runs", "updated_at"),
    ("documents", "created_at"),
    ("document_chunks", "created_at"),
    ("prompts", "created_at"),
    ("llm_calls", "created_at"),
]


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, column in _COLUMNS:
        op.alter_column(
            table,
            column,
            type_=sa.DateTime(timezone=True),
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, column in _COLUMNS:
        op.alter_column(
            table,
            column,
            type_=sa.DateTime(),
            # The inverse reading: express the instant in UTC, then drop the
            # offset — so a downgrade and a re-upgrade round-trip to the same
            # wall clock rather than drifting by the server's timezone.
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )
