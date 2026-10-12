"""add oauth tables

Revision ID: c4d2e8f1a9b3
Revises: a3f1c2d4e5b6
Create Date: 2026-10-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4d2e8f1a9b3'
down_revision: Union[str, None] = 'a3f1c2d4e5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'oauthclient',
        sa.Column('client_id', sa.String(), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('client_id'),
    )
    op.create_table(
        'oauthauthrequest',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('client_id', sa.String(), nullable=False),
        sa.Column('redirect_uri', sa.String(), nullable=False),
        sa.Column('scope', sa.String(), nullable=False),
        sa.Column('state', sa.String(), nullable=True),
        sa.Column('code_challenge', sa.String(), nullable=False),
        sa.Column('resource', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'oauthcode',
        sa.Column('code_hash', sa.String(), nullable=False),
        sa.Column('client_id', sa.String(), nullable=False),
        sa.Column('subject', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('redirect_uri', sa.String(), nullable=False),
        sa.Column('scopes', sa.JSON(), nullable=False),
        sa.Column('code_challenge', sa.String(), nullable=False),
        sa.Column('resource', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('code_hash'),
    )
    op.create_table(
        'oauthgrant',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('refresh_jti_hash', sa.String(), nullable=False),
        sa.Column('client_id', sa.String(), nullable=False),
        sa.Column('client_name', sa.String(), nullable=True),
        sa.Column('subject', sa.String(), nullable=False),
        sa.Column('scopes', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_oauthgrant_refresh_jti_hash', 'oauthgrant', ['refresh_jti_hash'], unique=True)
    op.create_index('ix_oauthgrant_client_id', 'oauthgrant', ['client_id'], unique=False)
    op.create_index('ix_oauthgrant_subject', 'oauthgrant', ['subject'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_oauthgrant_subject', table_name='oauthgrant')
    op.drop_index('ix_oauthgrant_client_id', table_name='oauthgrant')
    op.drop_index('ix_oauthgrant_refresh_jti_hash', table_name='oauthgrant')
    op.drop_table('oauthgrant')
    op.drop_table('oauthcode')
    op.drop_table('oauthauthrequest')
    op.drop_table('oauthclient')
