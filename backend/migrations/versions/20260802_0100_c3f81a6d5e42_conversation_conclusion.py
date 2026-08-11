"""conversation conclusion

A branch verdict says which exploration won. This says what the team now
believes — the thing someone asks for when they say "so what did we land on?".
Empty until a human writes it; Helix can draft it from the branches, but a
draft nobody accepted is not a conclusion.

Revision ID: c3f81a6d5e42
Revises: a1c7e9d4b2f0
Create Date: 2026-08-02 01:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3f81a6d5e42'
down_revision: Union[str, None] = 'a1c7e9d4b2f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('conversations', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('conclusion', sa.Text(), nullable=False, server_default='')
        )
        batch_op.add_column(sa.Column('concluded_by', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('concluded_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('conversations', schema=None) as batch_op:
        batch_op.drop_column('concluded_at')
        batch_op.drop_column('concluded_by')
        batch_op.drop_column('conclusion')
