"""agent_config quick replies

Revision ID: b6d2f8a4e317
Revises: a3b7e5d1c904
Create Date: 2026-10-15 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b6d2f8a4e317'
down_revision: Union[str, None] = 'a3b7e5d1c904'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'agent_config',
        sa.Column('quick_reply_enabled', sa.Boolean(), nullable=False, server_default='false'),
    )
    op.add_column(
        'agent_config',
        sa.Column('quick_fast_answer', sa.Boolean(), nullable=False, server_default='true'),
    )
    op.add_column(
        'agent_config',
        sa.Column('quick_filler', sa.Boolean(), nullable=False, server_default='true'),
    )
    op.add_column(
        'agent_config', sa.Column('quick_reply_model', sa.String(length=255), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('agent_config', 'quick_reply_model')
    op.drop_column('agent_config', 'quick_filler')
    op.drop_column('agent_config', 'quick_fast_answer')
    op.drop_column('agent_config', 'quick_reply_enabled')
