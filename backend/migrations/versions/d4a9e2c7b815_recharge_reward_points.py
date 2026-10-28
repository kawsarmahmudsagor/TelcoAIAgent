"""recharge_reward_points: points a recharge earned the payer

Revision ID: d4a9e2c7b815
Revises: c8f2a6d4e9b1
Create Date: 2026-10-28 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4a9e2c7b815'
down_revision: Union[str, None] = 'c8f2a6d4e9b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Earlier recharges earned nothing, so existing rows stay at 0.
    op.add_column(
        'transactions',
        sa.Column('points_earned', sa.Integer(), server_default='0', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('transactions', 'points_earned')
