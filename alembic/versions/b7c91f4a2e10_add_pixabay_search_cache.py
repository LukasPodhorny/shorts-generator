"""Cache Pixabay searches in Postgres when Redis is absent.

Revision ID: b7c91f4a2e10
Revises: 91d3a7e6c2b4
"""

from alembic import op
import sqlalchemy as sa


revision = "b7c91f4a2e10"
down_revision = "91d3a7e6c2b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pixabaysearchcache",
        sa.Column("cache_key", sa.String(120), primary_key=True),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("pixabaysearchcache")
