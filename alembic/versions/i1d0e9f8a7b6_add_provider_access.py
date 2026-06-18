"""add provider_access to profiles and system_config table

Revision ID: i1d0e9f8a7b6
Revises: h9c8d7e6f5a4
Create Date: 2026-06-17
"""
import sqlalchemy as sa
from alembic import op

revision = "i1d0e9f8a7b6"
down_revision = "b056a2e95e09"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "system_config",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
    )
    op.add_column("profiles", sa.Column("provider_access", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("profiles", "provider_access")
    op.drop_table("system_config")
