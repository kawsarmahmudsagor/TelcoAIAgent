import enum
from datetime import date

from sqlalchemy import Boolean, Date, Enum, Integer, Numeric, String, Text, false
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TimestampedBase


class PropertyType(str, enum.Enum):
    apartment = "apartment"
    studio = "studio"
    duplex = "duplex"
    commercial = "commercial"
    plot = "plot"


class ListingType(str, enum.Enum):
    rent = "rent"
    sale = "sale"


class Property(TimestampedBase):
    __tablename__ = "properties"

    title: Mapped[str] = mapped_column(String(255))
    address_line: Mapped[str] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(120))
    neighborhood: Mapped[str | None] = mapped_column(String(120), nullable=True)

    property_type: Mapped[PropertyType] = mapped_column(
        Enum(PropertyType, name="property_type")
    )
    listing_type: Mapped[ListingType] = mapped_column(Enum(ListingType, name="listing_type"))

    price: Mapped[float] = mapped_column(Numeric(12, 2))
    bedrooms: Mapped[int] = mapped_column(Integer)
    bathrooms: Mapped[float] = mapped_column(Numeric(3, 1))
    sqft: Mapped[int | None] = mapped_column(Integer, nullable=True)

    amenities: Mapped[list[str]] = mapped_column(JSONB, default=list)
    available_from: Mapped[date | None] = mapped_column(Date, nullable=True)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Cover image. `images` is the full ordered gallery, cover first.
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    images: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Hand-picked listings shown first on the public landing page.
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
