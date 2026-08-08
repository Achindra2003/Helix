"""remember which reasoning mode a paused run started in

Five reasoning presets ship in the engine, and until now the API pinned one
server-wide `.env` string, so the column was unnecessary — every run was the
same mode. Now a run carries its own, and a paused run rebuilt in a later
process has to come back in the mode it started in: the presets differ in depth,
energy curve, steer interval and all four prompts, so resuming into the instance
default would quietly change the kind of reasoning halfway through.

Empty means "the instance default", which is exactly what every row written
before this column existed meant.

Revision ID: f9c4d2a73b18
Revises: e7b3c95a1d84
Create Date: 2026-08-07 11:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f9c4d2a73b18'
down_revision: Union[str, None] = 'e7b3c95a1d84'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('resumable_runs', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('mode', sa.String(), nullable=False, server_default='')
        )


def downgrade() -> None:
    with op.batch_alter_table('resumable_runs', schema=None) as batch_op:
        batch_op.drop_column('mode')
