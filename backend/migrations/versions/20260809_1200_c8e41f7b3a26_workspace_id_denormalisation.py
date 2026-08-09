"""workspace_id down the branch/node subtree, and the key node_embeddings lacked

Groundwork for Row-Level Security (docs/DEPLOY-V1.md §A5), done as its own
change because it is a schema decision rather than a policy one, and because
the policies cannot be written until it is settled.

RLS needs a tenancy predicate per table. Fourteen tables already carry
`workspace_id` and take a one-line policy. Six did not, and reached it only by
joining: `branches` and `conversation_references` at one hop, `nodes` and
`branch_votes` at two, `node_citations` and `node_embeddings` at three. `nodes`
is one row per message — the hottest table in the product — so a policy that
subqueries three levels up would run on every read of every thread.

Denormalised rather than joined, for correctness before speed: a uniform
predicate is the one that stays right. The redundancy is only safe because it
cannot drift — NOT NULL, so a write site that forgets fails at commit instead
of writing a row no policy will match, and
`api/conversation/tests/test_workspace_id_denormalisation.py` checks every row
against its parent.

Added nullable, backfilled, then made NOT NULL: a table with rows cannot take a
NOT NULL column in one step, and there is no sensible server default for a
tenancy key. The backfill walks the same chain, top down, so each level is
populated before the level below reads it — correlated subqueries rather than
UPDATE...FROM, which SQLite does not have.

`node_embeddings.node_id` also becomes a real foreign key, ON DELETE CASCADE.
It was a bare string, so nothing prevented an embedding outliving its node —
and the cleanup that should have is in the router, running *after* the store
deletes the nodes, which a plain foreign key would have turned into a
violation. Cascade rather than another explicit delete, because unlike a
citation or a vote this row records nothing: it is a cache of the node's text,
meaningless once the text is gone.

Revision ID: c8e41f7b3a26
Revises: b6f30d7a4e51
Create Date: 2026-08-09 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c8e41f7b3a26'
down_revision: Union[str, None] = 'b6f30d7a4e51'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table, the SQL that finds its workspace). Ordered: each entry may rely on
# every entry above it already being backfilled.
_BACKFILL: list[tuple[str, str]] = [
    (
        "branches",
        "SELECT c.workspace_id FROM conversations c WHERE c.id = branches.conversation_id",
    ),
    (
        "conversation_references",
        "SELECT c.workspace_id FROM conversations c "
        "WHERE c.id = conversation_references.conversation_id",
    ),
    ("nodes", "SELECT b.workspace_id FROM branches b WHERE b.id = nodes.branch_id"),
    (
        "branch_votes",
        "SELECT b.workspace_id FROM branches b WHERE b.id = branch_votes.branch_id",
    ),
    (
        "node_citations",
        "SELECT n.workspace_id FROM nodes n WHERE n.id = node_citations.node_id",
    ),
    (
        "node_embeddings",
        "SELECT n.workspace_id FROM nodes n WHERE n.id = node_embeddings.node_id",
    ),
]

_TABLES = [table for table, _ in _BACKFILL]


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column("workspace_id", sa.String(), nullable=True))

    for table, lookup in _BACKFILL:
        # An orphan — a row whose parent is already gone — has no workspace to
        # inherit. Before this migration nothing stopped one existing, so they
        # are deleted rather than given a placeholder: a tenancy key that is a
        # lie is worse than a row that is missing, and the row was already
        # unreachable through every route (all of which start from a
        # workspace).
        op.execute(f"DELETE FROM {table} WHERE ({lookup}) IS NULL")
        op.execute(f"UPDATE {table} SET workspace_id = ({lookup})")

    for table in _TABLES:
        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column(
                "workspace_id", existing_type=sa.String(), nullable=False
            )
            batch_op.create_index(
                f"ix_{table}_workspace_id", ["workspace_id"], unique=False
            )

    # SQLite cannot add a constraint in place; batch mode recreates the table,
    # which is also the only way to attach a foreign key to an existing column.
    with op.batch_alter_table("node_embeddings") as batch_op:
        batch_op.create_foreign_key(
            "fk_node_embeddings_node_id", "nodes", ["node_id"], ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    with op.batch_alter_table("node_embeddings") as batch_op:
        batch_op.drop_constraint("fk_node_embeddings_node_id", type_="foreignkey")

    for table in _TABLES:
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_index(f"ix_{table}_workspace_id")
            batch_op.drop_column("workspace_id")
