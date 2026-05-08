"""add datasets

Revision ID: a8b7c6d5e4f3
Revises: f7a6b5c4d3e2
Create Date: 2026-05-07 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "a8b7c6d5e4f3"
down_revision = "f7a6b5c4d3e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "datasets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("embed_model", sa.String(100), nullable=False, server_default="nomic-embed-text"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_datasets_id", "datasets", ["id"])

    op.create_table(
        "dataset_files",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dataset_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dataset_files_id", "dataset_files", ["id"])

    with op.batch_alter_table("chats") as batch:
        batch.add_column(sa.Column("dataset_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_chats_dataset_id", "datasets", ["dataset_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("chats") as batch:
        batch.drop_constraint("fk_chats_dataset_id", type_="foreignkey")
        batch.drop_column("dataset_id")
    op.drop_index("ix_dataset_files_id", table_name="dataset_files")
    op.drop_table("dataset_files")
    op.drop_index("ix_datasets_id", table_name="datasets")
    op.drop_table("datasets")
