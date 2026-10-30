"""packages.auto_renewable

Revision ID: a9d4e2b7c518
Revises: c8e4a1f7d392
Create Date: 2026-10-29 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a9d4e2b7c518'
down_revision: Union[str, None] = 'c8e4a1f7d392'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# app.data.seed_telco.AUTO_RENEWABLE at the time of this migration.
_AUTO_RENEWABLE = (
    'D8-7D', 'D15-30D', 'D30-30D', 'D50-30D', 'D100-30D', 'V300-30D', 'V1000-30D',
    'B15-300', 'B40-500', 'B60-1000', 'S500-30D',
)


def upgrade() -> None:
    op.add_column(
        'packages',
        sa.Column('auto_renewable', sa.Boolean(), server_default='false', nullable=False),
    )
    packages = sa.table('packages', sa.column('code', sa.String), sa.column('auto_renewable', sa.Boolean))
    op.execute(
        packages.update()
        .where(packages.c.code.in_(_AUTO_RENEWABLE))
        .values(auto_renewable=True)
    )


def downgrade() -> None:
    op.drop_column('packages', 'auto_renewable')
