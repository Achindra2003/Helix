"""branch_votes — the move that answers forking

Forking was cheap and converging was not. A team could open four branches in a
minute; narrowing them again had no primitive at all, only prose. So threads
accumulated live alternatives nobody had ruled out, and the tree — the
product's signature — quietly became a pile of experiments instead of a
decision record.

`resolve_branch` already recorded verdicts, but a verdict is the *end* of
converging: one member writing down a conclusion the room never got to express
an opinion on. This is the reading taken before that.

Approval voting. A member may back any number of branches and backing one says
nothing about the others, because the honest signal in a design argument is
usually "either of these two works, the other two don't" rather than a ranking.
Forcing a ranking would manufacture a precision the room does not have. It also
keeps the write to a single insert instead of a read-modify-write across
siblings.

The unique constraint is the whole concurrency story: one member, one voice per
branch, enforced by the database rather than by a check-then-insert that two
tabs can both pass.

Revision ID: c7a13f6b2e08
Revises: b2d5e81c4f97
Create Date: 2026-08-08 15:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c7a13f6b2e08'
down_revision: Union[str, None] = 'b2d5e81c4f97'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'branch_votes',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('branch_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['branch_id'], ['branches.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('branch_id', 'user_id', name='uq_branch_votes_branch_user'),
    )
    op.create_index(op.f('ix_branch_votes_branch_id'), 'branch_votes', ['branch_id'])
    op.create_index(op.f('ix_branch_votes_user_id'), 'branch_votes', ['user_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_branch_votes_user_id'), table_name='branch_votes')
    op.drop_index(op.f('ix_branch_votes_branch_id'), table_name='branch_votes')
    op.drop_table('branch_votes')
