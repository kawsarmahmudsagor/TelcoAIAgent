"""offers: offers, offer_properties, offer_type enum

Revision ID: d6a2b9e4c1f8
Revises: c8e4f1a7d203
Create Date: 2026-10-13 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'd6a2b9e4c1f8'
down_revision: Union[str, None] = 'c8e4f1a7d203'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OFFER_TYPES = (
    'percent_discount',
    'flat_discount',
    'single_payment_discount',
    'installment_plan',
    'reduced_booking_money',
    'fee_waiver',
    'free_parking',
)


def upgrade() -> None:
    offer_type = postgresql.ENUM(*_OFFER_TYPES, name='offer_type', create_type=False)
    offer_type.create(op.get_bind(), checkfirst=True)
    op.create_table(
        'offers',
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('terms', sa.Text(), nullable=True),
        sa.Column('offer_type', offer_type, nullable=False),
        sa.Column('discount_percent', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('discount_amount', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('starts_on', sa.Date(), nullable=True),
        sa.Column('ends_on', sa.Date(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('applies_to_all_sale', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            'discount_percent IS NULL OR (discount_percent >= 0 AND discount_percent <= 100)',
            name='ck_offers_discount_percent_range',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'offer_properties',
        sa.Column('offer_id', sa.UUID(), nullable=False),
        sa.Column('property_id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['offer_id'], ['offers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['property_id'], ['properties.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('offer_id', 'property_id'),
    )
    # The batch lookup goes property -> offers; the PK only covers offer -> properties.
    op.create_index('ix_offer_properties_property_id', 'offer_properties', ['property_id'])


def downgrade() -> None:
    op.drop_index('ix_offer_properties_property_id', table_name='offer_properties')
    op.drop_table('offer_properties')
    op.drop_table('offers')
    sa.Enum(name='offer_type').drop(op.get_bind(), checkfirst=True)
