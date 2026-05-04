"""add_chat_discarded_at

Revision ID: f7a6b5c4d3e2
Revises: e6f5a4b3c2d1
Create Date: 2026-05-04 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'f7a6b5c4d3e2'
down_revision: Union[str, Sequence[str], None] = 'e6f5a4b3c2d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('chats', schema=None) as batch_op:
        batch_op.add_column(sa.Column('discarded_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('chats', schema=None) as batch_op:
        batch_op.drop_column('discarded_at')
