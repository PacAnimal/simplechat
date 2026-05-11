"""add dataset index_status and indexed_chunks columns

Revision ID: h9c8d7e6f5a4
Revises: g8b7c6d5e4f3
Create Date: 2026-05-11
"""
import sqlalchemy as sa
from alembic import op

revision = "h9c8d7e6f5a4"
down_revision = "g8b7c6d5e4f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("datasets") as batch_op:
        batch_op.add_column(sa.Column("index_status", sa.String(20), nullable=False, server_default="ready"))
        batch_op.add_column(sa.Column("indexed_chunks", sa.Integer, nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("datasets") as batch_op:
        batch_op.drop_column("indexed_chunks")
        batch_op.drop_column("index_status")
