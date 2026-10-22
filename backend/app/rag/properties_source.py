"""The `properties` knowledge-base source: one text document per active
listing, so general questions ("do you have anything with a rooftop in
Gulshan?") can be answered from the knowledge base too. search_apartments
stays the SQL search for filtered listing searches."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.property import Property
from app.rag.config import PROPERTY_ID_KEY
from app.rag.ingestion import TextDoc


def _money(value) -> str:
    return f"BDT {float(value):,.0f}"


def property_text(prop: Property) -> str:
    listing = "for rent" if prop.listing_type.value == "rent" else "for sale"
    price = _money(prop.price) + (" per month" if prop.listing_type.value == "rent" else "")
    area = ", ".join(part for part in (prop.neighborhood, prop.city) if part)
    lines = [
        f"### {prop.title}",
        "",
        f"{prop.property_type.value.capitalize()} {listing} in {area}. Price: {price}.",
    ]
    if prop.property_type.value != "plot":
        lines.append(f"Bedrooms: {prop.bedrooms}. Bathrooms: {float(prop.bathrooms):g}.")
    if prop.sqft:
        lines.append(f"Size: {prop.sqft} sqft.")
    if prop.amenities:
        lines.append("Amenities: " + ", ".join(a.replace("_", " ") for a in prop.amenities) + ".")
    if prop.available_from:
        lines.append(f"Available from {prop.available_from.isoformat()}.")
    if prop.description:
        lines.extend(["", prop.description.strip()])
    return "\n".join(lines)


def property_docs(db: Session, source_id: str) -> list[TextDoc]:
    """One TextDoc per active property, doc id `<source_id>:<property_id>`."""
    rows = db.scalars(
        select(Property).where(Property.is_active.is_(True)).order_by(Property.created_at)
    ).all()
    return [
        TextDoc(
            doc_id=f"{source_id}:{prop.id}",
            text=property_text(prop),
            metadata={PROPERTY_ID_KEY: str(prop.id), "property_title": prop.title},
        )
        for prop in rows
    ]
