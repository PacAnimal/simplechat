"""store cloud chats' model as a tier (chat / thinking) instead of a model ID

Revision ID: j2e1f0a9b8c7
Revises: i1d0e9f8a7b6
Create Date: 2026-10-11
"""
from alembic import op

revision = "j2e1f0a9b8c7"
down_revision = "i1d0e9f8a7b6"
branch_labels = None
depends_on = None


def upgrade():
    # top-tier and reasoning models go to thinking; everything else (incl. old Label@id aliases) to chat
    op.execute(
        """
        UPDATE chats SET model = CASE
            WHEN provider = 'anthropic' AND (model LIKE '%opus%' OR model LIKE '%fable%' OR model LIKE '%mythos%')
                THEN 'thinking'
            WHEN provider = 'openai' AND (
                model LIKE '%astra%' OR model LIKE '%-pro%'
                OR model LIKE 'o1%' OR model LIKE 'o3%' OR model LIKE 'o4%'
            )
                THEN 'thinking'
            ELSE 'chat'
        END
        WHERE provider IN ('openai', 'anthropic') AND model NOT IN ('chat', 'thinking')
        """
    )


def downgrade():
    # the original model IDs are gone; tiers keep resolving through config
    pass
