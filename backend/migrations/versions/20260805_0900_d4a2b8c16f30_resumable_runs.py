"""resumable runs

A paused run was held in a process-local dict, so a deploy or a reboot turned
"steer" into a 404 — and not a true one: the run had not finished and had not
expired, it had been forgotten. This table holds what it takes to build such a
run again, alongside the LangGraph checkpoint keyed by `thread_id`.

Rows exist only while a run is still owed a human answer; they are deleted the
moment it reaches a terminal state.

Revision ID: d4a2b8c16f30
Revises: c3f81a6d5e42
Create Date: 2026-08-05 09:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4a2b8c16f30'
down_revision: Union[str, None] = 'c3f81a6d5e42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'resumable_runs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('workspace_id', sa.String(), nullable=False),
        sa.Column('conversation_id', sa.String(), nullable=False),
        sa.Column('branch_id', sa.String(), nullable=False),
        sa.Column('author_id', sa.String(), nullable=False),
        sa.Column('shared', sa.Boolean(), nullable=False),
        sa.Column('thread_id', sa.String(), nullable=False),
        sa.Column('prompt', sa.Text(), nullable=False),
        sa.Column('steerable', sa.Boolean(), nullable=False),
        sa.Column('answer_parts', sa.Text(), nullable=False),
        sa.Column('events', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_resumable_runs_workspace_id'), 'resumable_runs', ['workspace_id']
    )
    op.create_index(
        op.f('ix_resumable_runs_conversation_id'), 'resumable_runs', ['conversation_id']
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_resumable_runs_conversation_id'), table_name='resumable_runs')
    op.drop_index(op.f('ix_resumable_runs_workspace_id'), table_name='resumable_runs')
    op.drop_table('resumable_runs')
