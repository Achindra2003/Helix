"""document metadata — turning a filename into a reference

A research team uploads papers and the index knew only filenames, so a citation
read `[smith-et-al-final-v3.pdf — part 4]`. That is not a citation: it names a
file on somebody's laptop, not a work another person can go and find. The
retrieval was good and the attribution was unusable, which is a strange way to
fail for the room the file-grounding feature was built for.

Four optional fields, none of them inferred. Extracting an author from PDF
metadata is wrong often enough that a confident wrong attribution would be
worse than a blank one — and attribution is the field a reader trusts most.
`identifier` is one column for DOI / arXiv id / URL rather than three that are
usually empty.

`node_citations.cite_as` is the same string frozen onto each citation at write
time, for the same reason the filename already was: an answer must keep saying
what it actually cited on the day it was written, even after the document is
recatalogued.

Revision ID: d8e42a97c135
Revises: c7a13f6b2e08
Create Date: 2026-08-08 16:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd8e42a97c135'
down_revision: Union[str, None] = 'c7a13f6b2e08'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default="" so existing rows get an empty string rather than NULL:
    # the model reads these as `str`, and a NULL would make every pre-existing
    # document raise on the first list request.
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('doc_title', sa.String(), nullable=False, server_default='')
        )
        batch_op.add_column(
            sa.Column('authors', sa.String(), nullable=False, server_default='')
        )
        batch_op.add_column(
            sa.Column('year', sa.String(), nullable=False, server_default='')
        )
        batch_op.add_column(
            sa.Column('identifier', sa.String(), nullable=False, server_default='')
        )
    with op.batch_alter_table('node_citations', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('cite_as', sa.String(), nullable=False, server_default='')
        )


def downgrade() -> None:
    with op.batch_alter_table('node_citations', schema=None) as batch_op:
        batch_op.drop_column('cite_as')
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.drop_column('identifier')
        batch_op.drop_column('year')
        batch_op.drop_column('authors')
        batch_op.drop_column('doc_title')
