"""node_citations — the evidence, made to outlast the tab

The `grounding` SSE frame reached the browser and stopped there: ChatView held
it in a module-level record, and a reload dropped it. The reply persisted, the
sources for it did not. For a product whose research claim is that an answer
can be traced back to the document it came from, that is the claim failing
quietly — the chips were there when you watched the answer arrive and gone
when you came back to check it.

A table, not a JSON column on `nodes`. The rendering question ("what did this
reply cite?") is answered equally well either way; the question that actually
distinguishes the research room ("which of our answers rest on this paper?")
is a query over `document_id`, and a blob cannot serve it.

`filename`, `score` and `excerpt` are copied in rather than joined. A citation
records what was true at the moment the claim was made: if the document is
renamed, re-chunked, or deleted, the old answer must keep saying what it
actually rested on. A live join would silently rewrite the record.

Revision ID: b2d5e81c4f97
Revises: a3f61c9d70e5
Create Date: 2026-08-08 14:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2d5e81c4f97'
down_revision: Union[str, None] = 'a3f61c9d70e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'node_citations',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('node_id', sa.String(), nullable=False),
        sa.Column('document_id', sa.String(), nullable=False),
        sa.Column('filename', sa.String(), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('score', sa.Float(), nullable=False),
        sa.Column('excerpt', sa.Text(), nullable=False),
        sa.Column('ordinal', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['node_id'], ['nodes.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    # Two reads, two indexes: rendering a thread fetches every citation for a
    # batch of node ids; the research question fetches every node citing a
    # document.
    op.create_index(
        op.f('ix_node_citations_node_id'), 'node_citations', ['node_id']
    )
    op.create_index(
        op.f('ix_node_citations_document_id'), 'node_citations', ['document_id']
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_node_citations_document_id'), table_name='node_citations')
    op.drop_index(op.f('ix_node_citations_node_id'), table_name='node_citations')
    op.drop_table('node_citations')
