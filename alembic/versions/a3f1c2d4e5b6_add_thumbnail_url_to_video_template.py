"""add_thumbnail_url_to_video_template

Revision ID: a3f1c2d4e5b6
Revises: 72917ce441b9
Create Date: 2026-04-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3f1c2d4e5b6'
down_revision: Union[str, None] = '72917ce441b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('videotemplate', sa.Column('thumbnail_url', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('videotemplate', 'thumbnail_url')
