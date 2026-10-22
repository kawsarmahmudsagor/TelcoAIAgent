"""Promotional offers on sale listings: price discounts and payment/fee perks,
managed in the dashboard and quoted by the agent through search_offers."""

import enum
import uuid
from datetime import date

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Table,
    Text,
    false,
    true,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampedBase
from app.models.property import Property


class OfferType(str, enum.Enum):
    # Price discounts.
    percent_discount = "percent_discount"
    flat_discount = "flat_discount"
    single_payment_discount = "single_payment_discount"
    # Payment and fee perks.
    installment_plan = "installment_plan"
    reduced_booking_money = "reduced_booking_money"
    fee_waiver = "fee_waiver"
    free_parking = "free_parking"


# The sale listings an offer is linked to (unused when applies_to_all_sale).
offer_properties = Table(
    "offer_properties",
    Base.metadata,
    Column(
        "offer_id",
        UUID(as_uuid=True),
        ForeignKey("offers.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "property_id",
        UUID(as_uuid=True),
        ForeignKey("properties.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Offer(TimestampedBase):
    __tablename__ = "offers"
    __table_args__ = (
        CheckConstraint(
            "discount_percent IS NULL OR (discount_percent >= 0 AND discount_percent <= 100)",
            name="ck_offers_discount_percent_range",
        ),
    )

    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    offer_type: Mapped[OfferType] = mapped_column(Enum(OfferType, name="offer_type"))
    discount_percent: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    # Taka.
    discount_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    # Inclusive calendar days in the agency's timezone; None = open-ended.
    starts_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    ends_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    applies_to_all_sale: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )

    properties: Mapped[list[Property]] = relationship(
        secondary=offer_properties, lazy="selectin", order_by=Property.title
    )

    @property
    def property_ids(self) -> list[uuid.UUID]:
        return [p.id for p in self.properties]
