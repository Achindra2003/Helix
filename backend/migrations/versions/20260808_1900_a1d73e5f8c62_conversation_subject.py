"""conversations.subject — what "this change" refers to

A dev team discusses "this change" for forty turns and never says the number.
That is fine between people and useless to an agent: with a GitHub tool
allowlisted it had everything it needed to read the pull request except which
pull request to read, so the first thing every agent run did was ask.

One free-text field, not a typed GitHub reference. What a thread is about is
not always a PR — it is an issue, a spec URL, a ticket — and a schema per
artifact kind would be building for a product we do not have. The value is
stated to the model as fact rather than instruction, because it is context.

Revision ID: a1d73e5f8c62
Revises: f5c81b3e29d4
Create Date: 2026-08-08 19:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1d73e5f8c62'
down_revision: Union[str, None] = 'f5c81b3e29d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default="" so existing threads read as "about nothing in
    # particular" rather than NULL — the model reads this as a `str`.
    with op.batch_alter_table('conversations', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('subject', sa.String(), nullable=False, server_default='')
        )


def downgrade() -> None:
    with op.batch_alter_table('conversations', schema=None) as batch_op:
        batch_op.drop_column('subject')
