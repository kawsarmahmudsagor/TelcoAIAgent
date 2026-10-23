"""audit_events subscriber set null

Revision ID: b54919f99fdf
Revises: d4e8a1c2f7b3
Create Date: 2026-10-23 10:48:30.612015

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b54919f99fdf'
down_revision: Union[str, None] = 'd4e8a1c2f7b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_FK = "audit_events_subscriber_id_fkey"


def _recreate(ondelete: str) -> None:
    op.drop_constraint(_FK, "audit_events", type_="foreignkey")
    op.create_foreign_key(
        _FK, "audit_events", "subscribers", ["subscriber_id"], ["id"], ondelete=ondelete
    )


def upgrade() -> None:
    _recreate("SET NULL")


def downgrade() -> None:
    _recreate("CASCADE")
