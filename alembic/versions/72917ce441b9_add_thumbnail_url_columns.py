"""add_thumbnail_url_columns

Revision ID: 72917ce441b9
Revises: 540b52515b5e
Create Date: 2026-04-04 12:11:04.995704

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '72917ce441b9'
down_revision: Union[str, None] = '540b52515b5e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add thumbnail_url column to reelseries table
    op.add_column('reelseries', sa.Column('thumbnail_url', sa.String(), nullable=True))

    # Add thumbnail_url column to reel table
    op.add_column('reel', sa.Column('thumbnail_url', sa.String(), nullable=True))


def downgrade() -> None:
    # Remove thumbnail_url column from reel table
    op.drop_column('reel', 'thumbnail_url')

    # Remove thumbnail_url column from reelseries table
    op.drop_column('reelseries', 'thumbnail_url')
