"""add call dial_number

Revision ID: c5e19a7d3f42
Revises: b4d8f2a61c37
Create Date: 2026-10-09 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c5e19a7d3f42'
down_revision: Union[str, None] = 'b4d8f2a61c37'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('call_schedule', sa.Column('dial_number', sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column('call_schedule', 'dial_number')
