"""agent_config.agency_phone / agency_address

Revision ID: a3b7e5d1c904
Revises: f4a8c2e6b913
Create Date: 2026-10-14 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a3b7e5d1c904'
down_revision: Union[str, None] = 'f4a8c2e6b913'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('agent_config', sa.Column('agency_phone', sa.String(length=50), nullable=True))
    op.add_column('agent_config', sa.Column('agency_address', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('agent_config', 'agency_address')
    op.drop_column('agent_config', 'agency_phone')
