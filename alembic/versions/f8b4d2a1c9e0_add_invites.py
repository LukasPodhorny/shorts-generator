"""Add approved invite emails.

Revision ID: f8b4d2a1c9e0
Revises: c4d2e8f1a9b3
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f8b4d2a1c9e0"
down_revision: Union[str, None] = "c4d2e8f1a9b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table("invite", sa.Column("email", sa.String(), nullable=False), sa.PrimaryKeyConstraint("email"))


def downgrade() -> None:
    op.drop_table("invite")
