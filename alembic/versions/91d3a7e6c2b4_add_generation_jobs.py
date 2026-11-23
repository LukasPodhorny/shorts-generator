"""Add durable generation jobs for a single web dyno.

Revision ID: 91d3a7e6c2b4
Revises: 6e8c2a9f4d10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "91d3a7e6c2b4"
down_revision: Union[str, None] = "6e8c2a9f4d10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "generationjob",
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("request_data", sa.JSON(), nullable=False),
        sa.Column("total_cost", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["series_id"], ["reelseries.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("series_id"),
    )


def downgrade() -> None:
    op.drop_table("generationjob")
