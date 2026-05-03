"""add_profiles

Revision ID: b3f2c1d4e5a6
Revises: 98e1687b675a
Create Date: 2026-05-03 20:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b3f2c1d4e5a6'
down_revision: Union[str, Sequence[str], None] = '98e1687b675a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'profiles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('avatar', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_profiles_name'),
    )
    with op.batch_alter_table('profiles', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_profiles_id'), ['id'], unique=False)

    with op.batch_alter_table('chats', schema=None) as batch_op:
        batch_op.add_column(sa.Column('profile_id', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('chats', schema=None) as batch_op:
        batch_op.drop_column('profile_id')

    with op.batch_alter_table('profiles', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_profiles_id'))

    op.drop_table('profiles')
