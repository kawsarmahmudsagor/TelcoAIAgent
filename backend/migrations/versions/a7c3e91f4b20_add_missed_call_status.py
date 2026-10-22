"""add missed call status

Revision ID: a7c3e91f4b20
Revises: d255d68eb32a
Create Date: 2026-10-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'a7c3e91f4b20'
down_revision: Union[str, None] = 'd255d68eb32a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE can't run inside a transaction block.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE call_status ADD VALUE IF NOT EXISTS 'missed'")


def downgrade() -> None:
    # Postgres enums can't drop a value in place -- fold missed calls into
    # cancelled, then recreate the type without 'missed' and swap the column over.
    op.execute("UPDATE call_schedule SET status = 'cancelled' WHERE status = 'missed'")
    op.execute("ALTER TYPE call_status RENAME TO call_status_old")
    op.execute(
        "CREATE TYPE call_status AS ENUM "
        "('pending', 'dispatched', 'in_progress', 'completed', 'failed', 'cancelled')"
    )
    op.execute(
        "ALTER TABLE call_schedule ALTER COLUMN status TYPE call_status "
        "USING status::text::call_status"
    )
    op.execute("DROP TYPE call_status_old")
