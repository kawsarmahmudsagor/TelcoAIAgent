"""Throwaway listings and offers for the offer tests. Everything is titled with
PREFIX and removed by that prefix, so the seeded offers and listings are never
touched."""

from sqlalchemy import text

from app.db.session import SessionLocal
from app.repositories import property_repo

PREFIX = "PYTEST-OFFERS"
# A made-up area no real listing is in, so location filters see only these.
AREA = "Pytestpur"


def make_property(title: str, *, listing_type: str = "sale", is_active: bool = True, area=AREA):
    db = SessionLocal()
    try:
        prop = property_repo.create(
            db,
            {
                "title": f"{PREFIX} {title}",
                "address_line": f"Road 7, {area}",
                "city": "Dhaka",
                "neighborhood": area,
                "property_type": "apartment",
                "listing_type": listing_type,
                "price": 9_500_000 if listing_type == "sale" else 30_000,
                "bedrooms": 3,
                "bathrooms": 2,
                "is_active": is_active,
            },
        )
        return prop.id
    finally:
        db.close()


def set_property(property_id, **fields) -> None:
    db = SessionLocal()
    try:
        property_repo.update_fields(db, property_repo.get(db, property_id), fields)
    finally:
        db.close()


def cleanup() -> None:
    db = SessionLocal()
    try:
        p = {"prefix": f"{PREFIX}%"}
        db.execute(text("delete from offers where title like :prefix"), p)
        db.execute(text("delete from properties where title like :prefix"), p)
        db.commit()
    finally:
        db.close()


def offer_payload(title: str, **overrides) -> dict:
    payload = {
        "title": f"{PREFIX} {title}",
        "offer_type": "flat_discount",
        "discount_amount": 500_000,
        "description": "Half a million off.",
        "terms": "Book within 7 days.",
    }
    payload.update(overrides)
    return payload
