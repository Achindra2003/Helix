"""branch lifecycle: intent and resolution

A branch could be created and never finished, so a tree of them recorded the
alternatives a team considered but never which one won. `intent` is what the
exploration was trying (asked at fork time); the resolution columns are what
came of it.

Existing rows get intent="" and status="open", which is truthful: nobody had
resolved them, because there was no way to.

Revision ID: a1c7e9d4b2f0
Revises: 25ebf6fcdc8e
Create Date: 2026-08-01 10:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1c7e9d4b2f0'
down_revision: Union[str, None] = '25ebf6fcdc8e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('branches', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('intent', sa.Text(), nullable=False, server_default='')
        )
        batch_op.add_column(
            sa.Column('status', sa.String(), nullable=False, server_default='open')
        )
        batch_op.add_column(
            sa.Column('resolution', sa.Text(), nullable=False, server_default='')
        )
        batch_op.add_column(sa.Column('resolved_by', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('resolved_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('branches', schema=None) as batch_op:
        batch_op.drop_column('resolved_at')
        batch_op.drop_column('resolved_by')
        batch_op.drop_column('resolution')
        batch_op.drop_column('status')
        batch_op.drop_column('intent')
