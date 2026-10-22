import enum
from datetime import date

from sqlalchemy import Date, Enum, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TimestampedBase


class LeadStatus(str, enum.Enum):
    new = "new"
    contacted = "contacted"
    qualified = "qualified"
    booked = "booked"
    closed = "closed"
    lost = "lost"


class RentOrBuy(str, enum.Enum):
    rent = "rent"
    buy = "buy"
    undecided = "undecided"


class Client(TimestampedBase):
    __tablename__ = "clients"

    full_name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    lead_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lead_status: Mapped[LeadStatus] = mapped_column(
        Enum(LeadStatus, name="lead_status"), default=LeadStatus.new
    )

    budget_min: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    budget_max: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    preferred_location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    preferred_property_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bedrooms_wanted: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bathrooms_wanted: Mapped[float | None] = mapped_column(Numeric(3, 1), nullable=True)
    move_in_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    rent_or_buy: Mapped[RentOrBuy] = mapped_column(
        Enum(RentOrBuy, name="rent_or_buy"), default=RentOrBuy.undecided
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
