"""notices — the bell, made to outlast the tab

The bell was a client-side store: a teammate's run finishing, a thread
concluding, all held in the page's memory and gone on reload. Nothing in the
product could address a *person* and have the message survive their closing the
laptop, which is a strange gap in something whose claim is that a team's
thinking is kept.

`notices` is one row per recipient per event — not one row per event with a
join table for who has read it — because "has this person seen it" is a fact
about the person. `read_at` is a nullable timestamp rather than a boolean
because the question after "have they seen it" is always "when".

Everything except `user_id` is denormalised on purpose: the bell renders a
notice without reading the conversation it points into, and a mention from a
member who has since been removed still reads correctly.

Revision ID: a3f61c9d70e5
Revises: f9c4d2a73b18
Create Date: 2026-08-08 09:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3f61c9d70e5'
down_revision: Union[str, None] = 'f9c4d2a73b18'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'notices',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('workspace_id', sa.String(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('actor_id', sa.String(), nullable=True),
        sa.Column('actor_email', sa.String(), nullable=False),
        sa.Column('conversation_id', sa.String(), nullable=False),
        sa.Column('branch_id', sa.String(), nullable=False),
        sa.Column('node_id', sa.String(), nullable=False),
        sa.Column('excerpt', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    # Every read is "my notices, newest first"; every write is one row.
    op.create_index(op.f('ix_notices_user_id'), 'notices', ['user_id'])
    op.create_index(op.f('ix_notices_workspace_id'), 'notices', ['workspace_id'])
    op.create_index(
        op.f('ix_notices_conversation_id'), 'notices', ['conversation_id']
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_notices_conversation_id'), table_name='notices')
    op.drop_index(op.f('ix_notices_workspace_id'), table_name='notices')
    op.drop_index(op.f('ix_notices_user_id'), table_name='notices')
    op.drop_table('notices')
