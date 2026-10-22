import re
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.data import localities
from app.models.property import ListingType, Property, PropertyType


def get(db: Session, property_id: uuid.UUID) -> Property | None:
    return db.get(Property, property_id)


def get_active(db: Session, property_id: uuid.UUID) -> Property | None:
    """A listing the public may see: None if it's missing or deactivated."""
    prop = db.get(Property, property_id)
    return prop if prop is not None and prop.is_active else None


def list_all(db: Session, limit: int = 100, offset: int = 0) -> list[Property]:
    stmt = select(Property).order_by(Property.created_at.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt))


def create(db: Session, data: dict) -> Property:
    prop = Property(**data)
    db.add(prop)
    db.commit()
    db.refresh(prop)
    return prop


# Columns an admin may clear by sending an explicit null; a null for any other
# field in a partial update just means "leave it alone".
_CLEARABLE_FIELDS = {"neighborhood", "sqft", "available_from", "description", "image_url", "images"}


def update_fields(db: Session, prop: Property, data: dict) -> Property:
    for key, value in data.items():
        if value is None and key not in _CLEARABLE_FIELDS:
            continue
        setattr(prop, key, value)
    db.commit()
    db.refresh(prop)
    return prop


def list_public(db: Session, *, limit: int, featured_only: bool = True) -> list[Property]:
    """Active listings for the public landing page, featured first."""
    stmt = select(Property).where(Property.is_active.is_(True))
    if featured_only:
        stmt = stmt.where(Property.is_featured.is_(True))
    stmt = stmt.order_by(Property.is_featured.desc(), Property.created_at.desc(), Property.title)
    return list(db.scalars(stmt.limit(limit)))


# Sort orders for the public "all properties" page. Every order ends on the id
# so pages never overlap or skip a listing when prices or dates tie.
PUBLIC_SORTS = {
    "featured": (Property.is_featured.desc(), Property.created_at.desc(), Property.id),
    "newest": (Property.created_at.desc(), Property.id),
    "price_asc": (Property.price.asc(), Property.id),
    "price_desc": (Property.price.desc(), Property.id),
}


def browse_public(
    db: Session,
    *,
    listing_type: ListingType | None = None,
    property_types: list[PropertyType] | None = None,
    area: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    min_bedrooms: int | None = None,
    min_bathrooms: float | None = None,
    sort: str = "featured",
    limit: int = 12,
    offset: int = 0,
) -> tuple[list[Property], int]:
    """One page of active listings matching the public filters, plus the total
    number that match. `area` is a city or a neighbourhood, matched exactly
    (case-insensitive): the options come from `public_facets`."""
    stmt = select(Property).where(Property.is_active.is_(True))
    if listing_type is not None:
        stmt = stmt.where(Property.listing_type == listing_type)
    if property_types:
        stmt = stmt.where(Property.property_type.in_(property_types))
    if area:
        key = area.strip().lower()
        stmt = stmt.where(
            or_(func.lower(Property.city) == key, func.lower(Property.neighborhood) == key)
        )
    if min_price is not None:
        stmt = stmt.where(Property.price >= min_price)
    if max_price is not None:
        stmt = stmt.where(Property.price <= max_price)
    if min_bedrooms is not None:
        stmt = stmt.where(Property.bedrooms >= min_bedrooms)
    if min_bathrooms is not None:
        stmt = stmt.where(Property.bathrooms >= min_bathrooms)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order = PUBLIC_SORTS.get(sort, PUBLIC_SORTS["featured"])
    page = db.scalars(stmt.order_by(*order).limit(limit).offset(offset))
    return list(page), total


def public_facets(db: Session) -> dict:
    """Filter options for the public listings page, from active listings only:
    cities and neighbourhoods with counts, counts per type, and price bounds
    per listing type (rents and sale prices are on very different scales)."""
    active = Property.is_active.is_(True)
    cities = db.execute(
        select(Property.city, func.count())
        .where(active)
        .group_by(Property.city)
        .order_by(func.count().desc(), Property.city)
    ).all()
    neighborhoods = db.execute(
        select(Property.neighborhood, Property.city, func.count())
        .where(active, Property.neighborhood.is_not(None), Property.neighborhood != "")
        .group_by(Property.neighborhood, Property.city)
        .order_by(Property.neighborhood, Property.city)
    ).all()
    types = db.execute(
        select(Property.property_type, func.count()).where(active).group_by(Property.property_type)
    ).all()
    prices = db.execute(
        select(
            Property.listing_type, func.min(Property.price), func.max(Property.price), func.count()
        )
        .where(active)
        .group_by(Property.listing_type)
    ).all()
    max_bedrooms = db.scalar(select(func.max(Property.bedrooms)).where(active)) or 0
    return {
        "total": sum(count for _, count in cities),
        "cities": [{"name": name, "count": count} for name, count in cities],
        "neighborhoods": [
            {"name": name, "city": city, "count": count} for name, city, count in neighborhoods
        ],
        "property_types": [{"value": t, "count": count} for t, count in types],
        "price_ranges": [
            {"listing_type": lt, "min": float(lo), "max": float(hi), "count": count}
            for lt, lo, hi, count in prices
        ],
        "max_bedrooms": max_bedrooms,
    }


# Commercial space and plots aren't homes: left in a generic search they crowd
# out flats in cheapest-first results, so they only show up when asked for.
_NON_RESIDENTIAL_TYPES = (PropertyType.commercial, PropertyType.plot)


def search(
    db: Session,
    *,
    budget_min: float | None = None,
    budget_max: float | None = None,
    location: str | None = None,
    property_type: PropertyType | None = None,
    listing_type: ListingType | None = None,
    bedrooms: int | None = None,
    bathrooms: float | None = None,
    amenities: list[str] | None = None,
    near_price: float | None = None,
    exclude_ids: set[uuid.UUID] | None = None,
    limit: int = 5,
) -> list[Property]:
    """Cheapest first, or closest to `near_price` first when it's given."""
    stmt = select(Property).where(Property.is_active.is_(True))
    if exclude_ids:
        stmt = stmt.where(Property.id.not_in(list(exclude_ids)))

    if budget_min is not None:
        stmt = stmt.where(Property.price >= budget_min)
    if budget_max is not None:
        stmt = stmt.where(Property.price <= budget_max)
    subarea = localities.get(name) if (name := localities.resolve_subarea(location)) else None
    if subarea is not None:
        # A sector or pocket ("Mirpur 12", "Lalmatia"): in the parent area, with
        # the sub-area named in the address. A word-boundary regex, so "Mirpur 1"
        # isn't Mirpur 10-14, and the parent check keeps Purbachal's "Sector 4"
        # out of Uttara Sector 4.
        parent = f"%{subarea.parent}%"
        stmt = stmt.where(
            or_(Property.neighborhood.ilike(parent), Property.address_line.ilike(parent)),
            Property.address_line.regexp_match(subarea.pattern, flags="i"),
        )
    elif location:
        # The LLM often sends a compound value like "Uttara, Dhaka" rather than a
        # bare neighborhood -- matching the whole string as one substring would
        # miss every row, since neither "Dhaka" nor "Uttara" alone contains it.
        # Require each comma/slash-separated token to match city or neighborhood
        # (AND across tokens, OR across columns per token) so "Uttara, Dhaka"
        # narrows to Uttara specifically instead of broadening to all of Dhaka.
        # address_line is matched too, so a sub-area the customer names ("Banani
        # DOHS", "Mirpur 10") finds listings whose neighborhood is just "Banani".
        tokens = [t.strip() for t in re.split(r"[,/]", location) if t.strip()] or [location]
        for token in tokens:
            pattern = f"%{token}%"
            stmt = stmt.where(
                or_(
                    Property.city.ilike(pattern),
                    Property.neighborhood.ilike(pattern),
                    Property.address_line.ilike(pattern),
                )
            )
    if property_type is not None:
        stmt = stmt.where(Property.property_type == property_type)
    else:
        stmt = stmt.where(Property.property_type.not_in(_NON_RESIDENTIAL_TYPES))
    if listing_type is not None:
        stmt = stmt.where(Property.listing_type == listing_type)
    if bedrooms is not None:
        stmt = stmt.where(Property.bedrooms >= bedrooms)
    if bathrooms is not None:
        stmt = stmt.where(Property.bathrooms >= bathrooms)
    if amenities:
        for amenity in amenities:
            stmt = stmt.where(Property.amenities.contains([amenity]))

    if near_price is not None:
        stmt = stmt.order_by(func.abs(Property.price - near_price), Property.price, Property.id)
    else:
        stmt = stmt.order_by(Property.price.asc())
    return list(db.scalars(stmt.limit(limit)))


def residential_price_ranges(db: Session) -> dict[ListingType, tuple[float, float]]:
    """(lowest, highest) active home price per listing type -- rent and sale
    sit on very different scales, so a budget alone usually says which one."""
    rows = db.execute(
        select(Property.listing_type, func.min(Property.price), func.max(Property.price))
        .where(
            Property.is_active.is_(True),
            Property.property_type.not_in(_NON_RESIDENTIAL_TYPES),
        )
        .group_by(Property.listing_type)
    ).all()
    return {ListingType(lt): (float(lo), float(hi)) for lt, lo, hi in rows}


def known_amenities(db: Session) -> set[str]:
    """Every amenity value any active listing actually records."""
    stmt = (
        select(func.jsonb_array_elements_text(Property.amenities))
        .where(Property.is_active.is_(True))
        .distinct()
    )
    return set(db.scalars(stmt))
