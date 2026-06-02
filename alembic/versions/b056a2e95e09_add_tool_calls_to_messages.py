"""add_tool_calls_to_messages

Revision ID: b056a2e95e09
Revises: h9c8d7e6f5a4
Create Date: 2026-06-02 13:09:38.315415

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b056a2e95e09'
down_revision: Union[str, Sequence[str], None] = 'h9c8d7e6f5a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tool_calls', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.drop_column('tool_calls')
