import uuid
from datetime import date, datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.offer import OfferType
from app.models.property import ListingType

# Offer types whose whole point is the percentage, and the one that is a fixed amount.
PERCENT_TYPES = {OfferType.percent_discount, OfferType.single_payment_discount}
AMOUNT_TYPES = {OfferType.flat_discount}


class OfferBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    terms: str | None = None
    offer_type: OfferType
    discount_percent: float | None = Field(default=None, ge=0, le=100)
    # Taka.
    discount_amount: float | None = Field(default=None, ge=0)
    starts_on: date | None = None
    ends_on: date | None = None
    is_active: bool = True
    applies_to_all_sale: bool = False
    # Sale listings it is linked to; ignored (cleared) when applies_to_all_sale.
    property_ids: list[uuid.UUID] = []

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.offer_type in PERCENT_TYPES and self.discount_percent is None:
            raise ValueError(f"{self.offer_type.value} needs discount_percent")
        if self.offer_type in AMOUNT_TYPES and self.discount_amount is None:
            raise ValueError(f"{self.offer_type.value} needs discount_amount")
        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            raise ValueError("ends_on must be on or after starts_on")
        if self.applies_to_all_sale:
            self.property_ids = []
        return self


class OfferCreate(OfferBase):
    pass


class OfferUpdate(BaseModel):
    """Partial update: the sent fields are merged onto the offer, and the result
    is validated as a whole (OfferCreate)."""

    title: str | None = None
    description: str | None = None
    terms: str | None = None
    offer_type: OfferType | None = None
    discount_percent: float | None = None
    discount_amount: float | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    is_active: bool | None = None
    applies_to_all_sale: bool | None = None
    property_ids: list[uuid.UUID] | None = None


class OfferPropertyOut(BaseModel):
    """A linked listing as the dashboard shows it, including ones that have since
    gone inactive or switched to rent (those no longer get the offer)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    city: str
    neighborhood: str | None = None
    listing_type: ListingType
    is_active: bool


class OfferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None = None
    terms: str | None = None
    offer_type: OfferType
    discount_percent: float | None = None
    discount_amount: float | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    is_active: bool
    applies_to_all_sale: bool
    property_ids: list[uuid.UUID]
    properties: list[OfferPropertyOut]
    created_at: datetime
    updated_at: datetime


class ListingOfferOut(BaseModel):
    """An offer as a listing's badge shows it (PublicListingOut.offers, chat cards)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    offer_type: OfferType
    discount_percent: float | None = None
    discount_amount: float | None = None
    ends_on: date | None = None


class OfferListingSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    city: str
    neighborhood: str | None = None
    price: float
    image_url: str | None = None


class PublicOfferOut(BaseModel):
    """A live offer for the public site. No internal flags."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None = None
    terms: str | None = None
    offer_type: OfferType
    discount_percent: float | None = None
    discount_amount: float | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    applies_to_all_sale: bool
    # Active sale listings it's linked to, at most 6; empty for an all-sale offer.
    listings: list[OfferListingSummary] = []
