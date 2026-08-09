"""document_corpus_revisions — a freshness check that does not cost the corpus

Retrieval now keeps a per-workspace scoring index in memory: the chunk vectors
as one float32 matrix, and BM25's postings. Both used to be rebuilt on every
single query — the dense arm decoded every stored vector into a Python list and
scored it with a generator expression, and BM25 re-tokenised the whole corpus to
answer one question. Measured, that is ~1.3 s of wait on one grounded send at
10,000 chunks, which is the size a literature review reaches, and it was paid
per message.

Caching the index moves the problem to knowing when it is stale. The obvious
probe is `COUNT(*)` plus `MAX(created_at)` over the workspace's chunks, and it
is the wrong primitive: counting walks every entry, so the check is O(corpus).
Measured at 50,000 chunks it was 120 ms — even with a covering index, and even
through plain synchronous sqlite3, so it is the scan and not the driver. The
freshness check cost more than the search it was protecting.

A counter is O(1) forever: one primary-key lookup returning one row. It lives in
the database rather than in process memory because a deployment runs more than
one worker, and an upload handled by worker A has to invalidate worker B's
cache — which B can only learn from shared state.

No backfill: a missing row reads as revision 0, and the first ingest or delete
in each workspace creates it. Existing workspaces therefore rebuild their index
once, on the first corpus change after this migration, which is exactly what
they would do anyway.
"""
from alembic import op
import sqlalchemy as sa

revision = "b6f30d7a4e51"
down_revision = "a1d73e5f8c62"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_corpus_revisions",
        # The workspace *is* the key: one corpus per workspace, one row.
        sa.Column("workspace_id", sa.String(), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("document_corpus_revisions")
