"""offer_audience_specific

Revision ID: c7a1f3e90b21
Revises: b54919f99fdf
Create Date: 2026-10-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'c7a1f3e90b21'
down_revision: Union[str, None] = 'b54919f99fdf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE offer_audience ADD VALUE IF NOT EXISTS 'specific'")
    op.create_table(
        'offer_subscribers',
        sa.Column('offer_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('subscriber_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(['offer_id'], ['offers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['subscriber_id'], ['subscribers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('offer_id', 'subscriber_id'),
    )


def downgrade() -> None:
    # Postgres cannot drop an enum value; 'specific' stays in the type.
    op.drop_table('offer_subscribers')
