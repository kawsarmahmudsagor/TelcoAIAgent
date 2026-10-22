"""add call answered_at

Revision ID: b4d8f2a61c37
Revises: a7c3e91f4b20
Create Date: 2026-10-05 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b4d8f2a61c37'
down_revision: Union[str, None] = 'a7c3e91f4b20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'call_schedule', sa.Column('answered_at', sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('call_schedule', 'answered_at')
