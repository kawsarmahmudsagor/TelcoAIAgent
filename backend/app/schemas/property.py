import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models.property import ListingType, PropertyType
from app.schemas.offer import ListingOfferOut


class PropertyBase(BaseModel):
    title: str
    address_line: str
    city: str
    neighborhood: str | None = None
    property_type: PropertyType
    listing_type: ListingType
    price: float
    bedrooms: int
    bathrooms: float
    sqft: int | None = None
    amenities: list[str] = []
    available_from: date | None = None
    description: str | None = None
    image_url: str | None = None
    images: list[str] | None = None
    is_active: bool = True
    is_featured: bool = False


class PropertyCreate(PropertyBase):
    pass


class PropertyUpdate(BaseModel):
    """Partial update: only the fields actually sent are changed."""

    title: str | None = None
    address_line: str | None = None
    city: str | None = None
    neighborhood: str | None = None
    property_type: PropertyType | None = None
    listing_type: ListingType | None = None
    price: float | None = None
    bedrooms: int | None = None
    bathrooms: float | None = None
    sqft: int | None = None
    amenities: list[str] | None = None
    available_from: date | None = None
    description: str | None = None
    image_url: str | None = None
    images: list[str] | None = None
    is_active: bool | None = None
    is_featured: bool | None = None


class PropertyOut(PropertyBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class PublicListingOut(BaseModel):
    """What the unauthenticated landing page may see: no street address and no
    internal flags (is_active, timestamps)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    city: str
    neighborhood: str | None = None
    property_type: PropertyType
    listing_type: ListingType
    price: float
    bedrooms: int
    bathrooms: float
    sqft: int | None = None
    amenities: list[str] = []
    available_from: date | None = None
    description: str | None = None
    image_url: str | None = None
    images: list[str] | None = None
    is_featured: bool = False
    # Live offers on this listing (sale listings only), filled by the route.
    offers: list[ListingOfferOut] = []


class PublicListingPage(BaseModel):
    """One page of the public "all properties" listing."""

    items: list[PublicListingOut]
    # How many active listings match the filters, across all pages.
    total: int
    limit: int
    offset: int


class FacetCount(BaseModel):
    name: str
    count: int


class NeighborhoodFacet(FacetCount):
    city: str


class PropertyTypeFacet(BaseModel):
    value: PropertyType
    count: int


class PriceRangeFacet(BaseModel):
    listing_type: ListingType
    min: float
    max: float
    count: int


class PublicListingFacets(BaseModel):
    """Filter options for the public listings page, drawn from active listings."""

    total: int
    cities: list[FacetCount]
    neighborhoods: list[NeighborhoodFacet]
    property_types: list[PropertyTypeFacet]
    price_ranges: list[PriceRangeFacet]
    max_bedrooms: int
