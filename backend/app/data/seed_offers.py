"""Sample offers in the style Dhaka developers run them: a cash-payment discount
on everything for sale, a fixed taka discount on a few flats, and an
installment plan with low booking money."""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.offer import Offer, OfferType
from app.models.property import ListingType, Property
from app.repositories.offer_repo import today

SAMPLE_OFFERS = [
    dict(
        title="Pay in full, save 5%",
        offer_type=OfferType.single_payment_discount,
        discount_percent=5,
        description="5% off the price when the full amount is paid in one go.",
        terms=(
            "Full payment within 30 days of signing the booking agreement. Not combinable "
            "with other offers. Registration and utility connection costs are extra."
        ),
        applies_to_all_sale=True,
        property_titles=[],
        ends_in_days=None,
    ),
    dict(
        title="Tk 10 lakh off on booking",
        offer_type=OfferType.flat_discount,
        discount_amount=1_000_000,
        description="10 lakh taka off the listed price for bookings made this season.",
        terms="Booking money of 10% within 7 days of the offer letter. One flat per buyer.",
        applies_to_all_sale=False,
        property_titles=[
            "Bashundhara Block D Family Flat",
            "Purbachal New Town 3BR Apartment",
        ],
        ends_in_days=60,
    ),
    dict(
        title="Book with 10%, pay over 36 months",
        offer_type=OfferType.installment_plan,
        discount_percent=None,
        description=(
            "Booking money of only 10%, then the balance in 36 equal monthly installments "
            "with no interest."
        ),
        terms="Post-dated cheques for the installments. Handover after the final installment.",
        applies_to_all_sale=False,
        property_titles=[
            "Uttara Sector 11 3BR Apartment for Sale",
            "Dhanmondi 2BR Starter Flat for Sale",
        ],
        ends_in_days=None,
    ),
]


def seed(db: Session) -> int:
    """Inserts the samples once: does nothing if any offer exists (an admin's
    edits and deletions are never undone). Returns the number inserted."""
    if db.scalar(select(Offer.id).limit(1)) is not None:
        return 0
    start = today()
    inserted = 0
    for sample in SAMPLE_OFFERS:
        data = dict(sample)
        titles = data.pop("property_titles")
        ends_in_days = data.pop("ends_in_days")
        properties = list(
            db.scalars(
                select(Property).where(
                    Property.title.in_(titles),
                    Property.is_active.is_(True),
                    Property.listing_type == ListingType.sale,
                )
            )
        )
        if titles and not properties:
            continue  # the listings it was written for are gone; skip it
        offer = Offer(
            **data,
            starts_on=start,
            ends_on=start + timedelta(days=ends_in_days) if ends_in_days else None,
            is_active=True,
        )
        offer.properties = properties
        db.add(offer)
        inserted += 1
    db.commit()
    return inserted
