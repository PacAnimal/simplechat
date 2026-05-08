"""drop dataset embed_model column

Revision ID: g8b7c6d5e4f3
Revises: a8b7c6d5e4f3
Create Date: 2026-05-08
"""
from alembic import op

revision = "g8b7c6d5e4f3"
down_revision = "a8b7c6d5e4f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("datasets") as batch_op:
        batch_op.drop_column("embed_model")


def downgrade() -> None:
    import sqlalchemy as sa
    with op.batch_alter_table("datasets") as batch_op:
        batch_op.add_column(sa.Column("embed_model", sa.String(100), nullable=False, server_default="nomic-embed-text"))
