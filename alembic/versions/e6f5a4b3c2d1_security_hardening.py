"""security_hardening

Revision ID: e6f5a4b3c2d1
Revises: d5e4f3a2b1c0
Create Date: 2026-05-04 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e6f5a4b3c2d1'
down_revision: Union[str, Sequence[str], None] = 'd5e4f3a2b1c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('profiles', schema=None) as batch_op:
        batch_op.add_column(sa.Column('token_invalidated_at', sa.DateTime(), nullable=True))

    op.execute("DELETE FROM chats WHERE profile_id IS NULL")
    with op.batch_alter_table('chats', schema=None) as batch_op:
        batch_op.alter_column('profile_id', existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table('chats', schema=None) as batch_op:
        batch_op.alter_column('profile_id', existing_type=sa.Integer(), nullable=True)

    with op.batch_alter_table('profiles', schema=None) as batch_op:
        batch_op.drop_column('token_invalidated_at')
