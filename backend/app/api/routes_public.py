import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.property import ListingType, Property, PropertyType
from app.repositories import agent_config_repo, offer_repo, property_repo
from app.schemas.offer import ListingOfferOut, OfferListingSummary, PublicOfferOut
from app.schemas.property import PublicListingFacets, PublicListingOut, PublicListingPage
from app.services import agent_config_service

# Unauthenticated: feeds the public landing page. Keep the response schema
# free of street addresses and internal fields.
router = APIRouter(prefix="/api/public", tags=["public"])

MAX_PUBLIC_LISTINGS = 24
# Page size cap for /listings/browse.
MAX_BROWSE_PAGE = 48
MAX_PUBLIC_OFFERS = 24
# Linked listings shown with each offer on the public site.
MAX_OFFER_LISTINGS = 6


class PublicAgentInfo(BaseModel):
    assistant_name: str
    agency_name: str


@router.get("/listings", response_model=list[PublicListingOut])
def list_public_listings(
    db: Session = Depends(get_db),
    limit: int = Query(6, ge=1),
    featured: bool = True,
) -> list:
    props = property_repo.list_public(
        db, limit=min(limit, MAX_PUBLIC_LISTINGS), featured_only=featured
    )
    return _with_offers(db, props)


PublicSort = Literal["featured", "newest", "price_asc", "price_desc"]


# Declared before /listings/{listing_id} so "browse" and "facets" aren't read as ids.
@router.get("/listings/browse", response_model=PublicListingPage)
def browse_public_listings(
    db: Session = Depends(get_db),
    listing_type: ListingType | None = None,
    property_type: Annotated[list[PropertyType] | None, Query()] = None,
    area: str | None = Query(None, max_length=120),
    min_price: float | None = Query(None, ge=0),
    max_price: float | None = Query(None, ge=0),
    min_bedrooms: int | None = Query(None, ge=0),
    min_bathrooms: float | None = Query(None, ge=0),
    sort: PublicSort = "featured",
    limit: int = Query(12, ge=1, le=MAX_BROWSE_PAGE),
    offset: int = Query(0, ge=0),
) -> PublicListingPage:
    """Every active listing (featured or not), filtered, sorted and paged, with
    the total number of matches. Feeds the public "all properties" page."""
    props, total = property_repo.browse_public(
        db,
        listing_type=listing_type,
        property_types=property_type,
        area=area,
        min_price=min_price,
        max_price=max_price,
        min_bedrooms=min_bedrooms,
        min_bathrooms=min_bathrooms,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return PublicListingPage(items=_with_offers(db, props), total=total, limit=limit, offset=offset)


@router.get("/listings/facets", response_model=PublicListingFacets)
def public_listing_facets(db: Session = Depends(get_db)) -> PublicListingFacets:
    """The options the public listings page's filters offer."""
    return PublicListingFacets.model_validate(property_repo.public_facets(db))


def _with_offers(db: Session, props: list[Property]) -> list[PublicListingOut]:
    offers = offer_repo.live_for_properties(db, [p.id for p in props])
    return [
        PublicListingOut.model_validate(p).model_copy(
            update={"offers": [ListingOfferOut.model_validate(o) for o in offers.get(p.id, [])]}
        )
        for p in props
    ]


# A plain str rather than uuid.UUID: a malformed id is just a page that doesn't
# exist (404), not a validation error (422).
@router.get("/listings/{listing_id}", response_model=PublicListingOut)
def get_public_listing(listing_id: str, db: Session = Depends(get_db)):
    try:
        parsed = uuid.UUID(listing_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="listing not found") from None
    prop = property_repo.get_active(db, parsed)
    if prop is None:
        raise HTTPException(status_code=404, detail="listing not found")
    return _with_offers(db, [prop])[0]


@router.get("/offers", response_model=list[PublicOfferOut])
def list_public_offers(db: Session = Depends(get_db)) -> list[PublicOfferOut]:
    """Live offers, each with up to 6 of the active sale listings it's linked to."""
    return [
        PublicOfferOut.model_validate(offer).model_copy(
            update={
                "listings": [
                    OfferListingSummary.model_validate(p)
                    for p in offer_repo.live_listings(offer, MAX_OFFER_LISTINGS)
                ]
            }
        )
        for offer in offer_repo.list_live(db, limit=MAX_PUBLIC_OFFERS)
    ]


@router.get("/agent-info", response_model=PublicAgentInfo)
def get_agent_info(db: Session = Depends(get_db)) -> PublicAgentInfo:
    """The names the agent introduces itself with, resolved the same way a call
    resolves them (dashboard values, else env defaults). Nothing secret."""
    config = agent_config_service.resolve(agent_config_repo.get(db))
    return PublicAgentInfo(assistant_name=config.assistant_name, agency_name=config.agency_name)
