"""subscriber_password_hash

Revision ID: d2e8b4a61f07
Revises: c7a1f3e90b21
Create Date: 2026-10-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd2e8b4a61f07'
down_revision: Union[str, None] = 'c7a1f3e90b21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('subscribers', sa.Column('password_hash', sa.String(length=60), nullable=True))


def downgrade() -> None:
    op.drop_column('subscribers', 'password_hash')
