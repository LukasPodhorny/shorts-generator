"""Add unguessable public share tokens to reels.

Revision ID: 6e8c2a9f4d10
Revises: f8b4d2a1c9e0
"""

from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision: str = "6e8c2a9f4d10"
down_revision: Union[str, None] = "f8b4d2a1c9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("reel", sa.Column("share_token", sa.String(length=32), nullable=True))
    connection = op.get_bind()
    for reel_id in connection.execute(sa.text("SELECT id FROM reel")).scalars().all():
        connection.execute(
            sa.text("UPDATE reel SET share_token = :token WHERE id = :id"),
            {"token": uuid4().hex, "id": reel_id},
        )
    with op.batch_alter_table("reel") as batch_op:
        batch_op.alter_column("share_token", existing_type=sa.String(length=32), nullable=False)
    op.create_index("ix_reel_share_token", "reel", ["share_token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_reel_share_token", table_name="reel")
    op.drop_column("reel", "share_token")
