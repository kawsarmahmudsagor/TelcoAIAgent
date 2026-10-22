"""Offers on sale listings.

"Live" is decided at query time: the offer is active, today (in the agency's
timezone) is inside its date window, and it reaches at least one listing that
is *still* active and for sale -- a linked listing that has since switched to
rent or been deactivated silently drops out rather than needing a cleanup job.
"""

import re
import uuid
from collections import defaultdict
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.offer import Offer, OfferType, offer_properties
from app.models.property import ListingType, Property
from app.services.taka import format_taka


class OfferValidationError(ValueError):
    """Linked listings that can't carry an offer (missing, inactive or for rent)."""


def agency_tz() -> ZoneInfo:
    # Same as app.agent.tools._datetime.agency_tz, without importing the agent's
    # tools package (and livekit) into the API process.
    return ZoneInfo(get_settings().agency_timezone)


def today() -> date:
    """Today's date in the agency's timezone: an offer ending "on the 15th" runs
    to the end of the 15th in Dhaka, not in UTC."""
    return datetime.now(agency_tz()).date()


def get(db: Session, offer_id: uuid.UUID) -> Offer | None:
    return db.get(Offer, offer_id)


def list_all(db: Session) -> list[Offer]:
    stmt = select(Offer).order_by(Offer.created_at.desc(), Offer.title)
    return list(db.scalars(stmt))


def _sale_properties(db: Session, ids: list[uuid.UUID]) -> list[Property]:
    """The listings for these ids; raises unless every one is an active sale listing."""
    unique = list(dict.fromkeys(ids))
    if not unique:
        return []
    found = {p.id: p for p in db.scalars(select(Property).where(Property.id.in_(unique)))}
    missing = [str(i) for i in unique if i not in found]
    if missing:
        raise OfferValidationError(f"Unknown listing id(s): {', '.join(missing)}")
    bad = [
        p.title
        for p in found.values()
        if not p.is_active or p.listing_type != ListingType.sale
    ]
    if bad:
        raise OfferValidationError(
            "Offers apply to active sale listings only; not: " + "; ".join(sorted(bad))
        )
    return [found[i] for i in unique]


def _apply(db: Session, offer: Offer, data: dict) -> None:
    property_ids = data.pop("property_ids", None)
    for key, value in data.items():
        setattr(offer, key, value)
    if offer.applies_to_all_sale:
        offer.properties = []
    elif property_ids is not None:
        offer.properties = _sale_properties(db, property_ids)


def create(db: Session, data: dict) -> Offer:
    offer = Offer()
    try:
        _apply(db, offer, dict(data))
    except OfferValidationError:
        db.rollback()
        raise
    db.add(offer)
    db.commit()
    db.refresh(offer)
    return offer


def update(db: Session, offer: Offer, data: dict) -> Offer:
    """`data` is the full, validated offer (OfferCreate). Listings linked earlier
    that have since stopped being active sale listings may stay linked (they
    just don't get the offer), so only newly added ids are checked."""
    data = dict(data)
    property_ids = data.get("property_ids")
    if property_ids is not None and not data.get("applies_to_all_sale"):
        current = {p.id: p for p in offer.properties}
        new_ids = [i for i in property_ids if i not in current]
        try:
            added = {p.id: p for p in _sale_properties(db, new_ids)}
        except OfferValidationError:
            db.rollback()
            raise
        data.pop("property_ids")
        for key, value in data.items():
            setattr(offer, key, value)
        offer.properties = [current.get(i) or added[i] for i in dict.fromkeys(property_ids)]
    else:
        _apply(db, offer, data)
    db.commit()
    db.refresh(offer)
    return offer


def delete(db: Session, offer: Offer) -> None:
    db.delete(offer)
    db.commit()


# ---- live offers ----


def _live_window(on: date):
    return and_(
        Offer.is_active.is_(True),
        or_(Offer.starts_on.is_(None), Offer.starts_on <= on),
        or_(Offer.ends_on.is_(None), Offer.ends_on >= on),
    )


def _on_sale():
    return and_(Property.is_active.is_(True), Property.listing_type == ListingType.sale)


def _location_filter(location: str | None, city: str | None, neighborhood: str | None):
    """Same token matching as property_repo.search: every comma-separated token
    must match the city, area or street."""
    clauses = []
    if city:
        clauses.append(Property.city.ilike(f"%{city.strip()}%"))
    if neighborhood:
        clauses.append(Property.neighborhood.ilike(f"%{neighborhood.strip()}%"))
    if location:
        tokens = [t.strip() for t in re.split(r"[,/]", location) if t.strip()] or [location]
        for token in tokens:
            pattern = f"%{token}%"
            clauses.append(
                or_(
                    Property.city.ilike(pattern),
                    Property.neighborhood.ilike(pattern),
                    Property.address_line.ilike(pattern),
                )
            )
    return clauses


def list_live(
    db: Session,
    *,
    property_id: uuid.UUID | None = None,
    location: str | None = None,
    city: str | None = None,
    neighborhood: str | None = None,
    offer_type: OfferType | None = None,
    limit: int = 20,
) -> list[Offer]:
    """Live offers that reach at least one active sale listing matching the
    filters: all-sale offers through any such listing, linked offers through
    their own listings."""
    eligible = [_on_sale(), *_location_filter(location, city, neighborhood)]
    if property_id is not None:
        eligible.append(Property.id == property_id)

    any_eligible = exists(select(Property.id).where(*eligible))
    linked_eligible = exists(
        select(offer_properties.c.property_id)
        .join(Property, Property.id == offer_properties.c.property_id)
        .where(offer_properties.c.offer_id == Offer.id, *eligible)
    )
    stmt = select(Offer).where(
        _live_window(today()),
        or_(and_(Offer.applies_to_all_sale.is_(True), any_eligible), linked_eligible),
    )
    if offer_type is not None:
        stmt = stmt.where(Offer.offer_type == offer_type)
    stmt = stmt.order_by(Offer.ends_on.asc().nulls_last(), Offer.created_at.desc()).limit(limit)
    return list(db.scalars(stmt))


def live_listings(offer: Offer, limit: int = 6) -> list[Property]:
    """The linked listings that currently get this offer."""
    return [
        p for p in offer.properties if p.is_active and p.listing_type == ListingType.sale
    ][:limit]


def live_for_properties(
    db: Session, ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[Offer]]:
    """Live offers per listing, for a batch of listings (rent or inactive ones get none)."""
    result: dict[uuid.UUID, list[Offer]] = defaultdict(list)
    ids = list(dict.fromkeys(ids))
    if not ids:
        return result
    sale_ids = set(db.scalars(select(Property.id).where(Property.id.in_(ids), _on_sale())))
    if not sale_ids:
        return result
    window = _live_window(today())
    all_sale = list(
        db.scalars(
            select(Offer)
            .where(window, Offer.applies_to_all_sale.is_(True))
            .order_by(Offer.ends_on.asc().nulls_last(), Offer.created_at.desc())
        )
    )
    linked = db.execute(
        select(offer_properties.c.property_id, Offer)
        .join(Offer, Offer.id == offer_properties.c.offer_id)
        .where(
            window,
            Offer.applies_to_all_sale.is_(False),
            offer_properties.c.property_id.in_(sale_ids),
        )
        .order_by(Offer.ends_on.asc().nulls_last(), Offer.created_at.desc())
    ).all()
    for property_id, offer in linked:
        result[property_id].append(offer)
    for property_id in sale_ids:
        result[property_id].extend(all_sale)
    return result


# ---- wording shared by the agent and the chat cards ----

_TYPE_LABELS = {
    OfferType.percent_discount: "discount",
    OfferType.flat_discount: "flat discount",
    OfferType.single_payment_discount: "single-payment discount",
    OfferType.installment_plan: "installment plan",
    OfferType.reduced_booking_money: "reduced booking money",
    OfferType.fee_waiver: "fee waiver",
    OfferType.free_parking: "free parking",
}


def describe(offer: Offer) -> str:
    """One-line wording for the LLM, prices in taka (not ৳, which the LLM copies)."""
    label = _TYPE_LABELS[offer.offer_type]
    parts = []
    if offer.discount_percent is not None:
        parts.append(f"{float(offer.discount_percent):g}% off")
    if offer.discount_amount is not None:
        verb = "off" if offer.offer_type == OfferType.flat_discount else ""
        # Offers are on sale listings only, so amounts are in lakh/crore.
        parts.append(f"{format_taka(offer.discount_amount, sale=True)} {verb}".strip())
    detail = f"{label}, {', '.join(parts)}" if parts else label
    return f"{offer.title} ({detail})"


def badge(offer: Offer) -> dict:
    """An offer as the chat card's badge needs it (same fields as ListingOfferOut)."""
    return {
        "id": str(offer.id),
        "title": offer.title,
        "offer_type": offer.offer_type.value,
        "discount_percent": (
            float(offer.discount_percent) if offer.discount_percent is not None else None
        ),
        "discount_amount": (
            float(offer.discount_amount) if offer.discount_amount is not None else None
        ),
        "ends_on": offer.ends_on.isoformat() if offer.ends_on else None,
    }
