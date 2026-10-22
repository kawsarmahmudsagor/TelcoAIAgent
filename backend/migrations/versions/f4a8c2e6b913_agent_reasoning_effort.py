"""agent_config.reasoning_effort

Revision ID: f4a8c2e6b913
Revises: e2f9a4c7b6d1
Create Date: 2026-10-13 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'f4a8c2e6b913'
down_revision: Union[str, None] = 'e2f9a4c7b6d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('agent_config', sa.Column('reasoning_effort', sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column('agent_config', 'reasoning_effort')
