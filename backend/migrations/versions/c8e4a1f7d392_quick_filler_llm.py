"""agent_config quick_filler_llm

Revision ID: c8e4a1f7d392
Revises: d4a9e2c7b815
Create Date: 2026-10-29 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c8e4a1f7d392'
down_revision: Union[str, None] = 'd4a9e2c7b815'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'agent_config',
        sa.Column('quick_filler_llm', sa.Boolean(), nullable=False, server_default='true'),
    )


def downgrade() -> None:
    op.drop_column('agent_config', 'quick_filler_llm')
