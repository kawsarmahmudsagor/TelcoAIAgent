"""agent_voice_replies

Revision ID: e5b9c3d72a14
Revises: d2e8b4a61f07
Create Date: 2026-10-26 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5b9c3d72a14'
down_revision: Union[str, None] = 'd2e8b4a61f07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'agent_config',
        sa.Column('voice_replies_enabled', sa.Boolean(), server_default='true', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('agent_config', 'voice_replies_enabled')
