"""tool_calls — the agent layer gets the instruments the LLM layer already had

`llm_calls` has answered "what did this workspace spend" since the telemetry
pass. The tool layer had nothing: `run_tools` executed a handler, caught what
came back, and returned a string, so the only record a call ever happened was a
400-character preview on a stream nobody kept. Approvals — the product's entire
safety claim — left no trace at all.

That gap is survivable while the catalog is three functions we wrote ourselves.
It stops being survivable the moment MCP lands, because then the workspace runs
tools written by someone else against someone else's server, and "which tool
did what, on whose approval, and how long did it take" is the question you
cannot answer during an incident. Hence this landing first.

**Arguments are digested, not stored.** A tool's arguments routinely contain
workspace content — a search query is a sentence someone typed. This is an
operational record, not a second copy of the conversation, so it keeps a short
hash: enough to tell two calls apart and see a model stuck in a retry loop,
useless for reading anyone's data back out.

`denied` is a status, not an error. A human refusing a tool is the approval
gate working; counting it as a failure would make the safety feature look like
a fault in every dashboard built on this table.

Revision ID: e4b96c2d17af
Revises: d8e42a97c135
Create Date: 2026-08-08 17:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e4b96c2d17af'
down_revision: Union[str, None] = 'd8e42a97c135'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tool_calls',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('workspace_id', sa.String(), nullable=False),
        sa.Column('run_id', sa.String(), nullable=False),
        sa.Column('tool_name', sa.String(), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('error', sa.String(), nullable=False),
        sa.Column('latency_ms', sa.Integer(), nullable=False),
        sa.Column('result_chars', sa.Integer(), nullable=False),
        sa.Column('args_digest', sa.String(), nullable=False),
        sa.Column('decided_by', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    # Three questions this table exists to answer, one index each: what has
    # this workspace been running, what happened during that run, and how does
    # this one tool behave.
    op.create_index(op.f('ix_tool_calls_workspace_id'), 'tool_calls', ['workspace_id'])
    op.create_index(op.f('ix_tool_calls_run_id'), 'tool_calls', ['run_id'])
    op.create_index(op.f('ix_tool_calls_tool_name'), 'tool_calls', ['tool_name'])


def downgrade() -> None:
    op.drop_index(op.f('ix_tool_calls_tool_name'), table_name='tool_calls')
    op.drop_index(op.f('ix_tool_calls_run_id'), table_name='tool_calls')
    op.drop_index(op.f('ix_tool_calls_workspace_id'), table_name='tool_calls')
    op.drop_table('tool_calls')
