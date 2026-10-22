"""booking_channel 'dashboard' (viewings booked by hand on the dashboard)

Revision ID: c8e1a4f7d2b5
Revises: b6d2f8a4e317
Create Date: 2026-10-15 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'c8e1a4f7d2b5'
down_revision: Union[str, None] = 'b6d2f8a4e317'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE can't run inside a transaction block.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE booking_channel ADD VALUE IF NOT EXISTS 'dashboard'")


def downgrade() -> None:
    # Postgres can't drop an enum value; move its rows to a kept value instead.
    op.execute(
        "UPDATE bookings SET channel = 'outbound_coldcall' WHERE channel = 'dashboard'"
    )
