import uuid

from livekit.agents import RunContext, function_tool
from livekit.agents.llm import ToolError

from app.agent.tools.search_apartments import _BANGLA_SCRIPT
from app.agent.userdata import SessionUserdata
from app.db.session import SessionLocal
from app.models.offer import OfferType
from app.repositories import offer_repo

_MAX_OFFERS = 8
_MAX_LISTINGS_PER_OFFER = 3

_OFFER_TYPE_SYNONYMS = {
    "discount": None,
    "percent": "percent_discount",
    "percentage": "percent_discount",
    "flat": "flat_discount",
    "cash_discount": "single_payment_discount",
    "single_payment": "single_payment_discount",
    "full_payment": "single_payment_discount",
    "installment": "installment_plan",
    "installments": "installment_plan",
    "emi": "installment_plan",
    "booking_money": "reduced_booking_money",
    "down_payment": "reduced_booking_money",
    "fee": "fee_waiver",
    "registration": "fee_waiver",
    "parking": "free_parking",
}

_GUARDRAIL = (
    "Quote only these offers, exactly as worded here. Unless the customer asked for an offer's "
    "details, terms or breakdown, name each offer in a few words (its amount and what it's for) "
    "and leave out its terms, conditions and end date. Never invent, "
    "combine, estimate or negotiate a discount, and never promise one that isn't listed; for "
    "anything else (a bigger discount, a custom deal) point them to the team's phone and head "
    "office, as WHAT YOU KNOW says."
)


def _parse_offer_type(raw: str) -> OfferType | None:
    key = raw.strip().lower().replace("-", "_").replace(" ", "_")
    if key in _OFFER_TYPE_SYNONYMS:
        mapped = _OFFER_TYPE_SYNONYMS[key]
        return OfferType(mapped) if mapped else None
    try:
        return OfferType(key)
    except ValueError:
        valid = ", ".join(t.value for t in OfferType)
        raise ToolError(
            f"Unknown offer_type {raw!r}. Use one of: {valid}, or leave it out."
        ) from None


def _listing_ref(shown: dict[int, dict], property_id: uuid.UUID, title: str, area: str) -> str:
    for number, card in shown.items():
        if card["id"] == str(property_id):
            return f"#{number} {title} ({area})"
    return f"{title} ({area})"


@function_tool()
async def search_offers(
    ctx: RunContext[SessionUserdata],
    listing_number: int | None = None,
    location: str | None = None,
    offer_type: str | None = None,
) -> str:
    """Find the current offers on sale listings: price discounts and payment or fee perks
    (installment plans, reduced booking money, fee waivers, free parking). Call it whenever the
    customer asks about offers, discounts, deals or whether a price is negotiable. Offers apply
    to listings for sale only, never to rentals.

    Args:
        listing_number: A listing's #number from search_apartments (or the one being viewed),
            to get only the offers on that listing.
        location: City or area, in English spelling, to get offers on listings there.
        offer_type: Only this kind: percent_discount, flat_discount, single_payment_discount,
            installment_plan, reduced_booking_money, fee_waiver or free_parking.
    """
    return await run_offers(
        ctx.userdata, listing_number=listing_number, location=location, offer_type=offer_type
    )


async def run_offers(
    userdata: SessionUserdata,
    *,
    listing_number: int | None = None,
    location: str | None = None,
    offer_type: str | None = None,
) -> str:
    """search_offers without the tool wrapper, for the turn router. Raises
    ToolError on arguments the tool would refuse."""
    if location and _BANGLA_SCRIPT.search(location):
        raise ToolError(
            "location must be in English spelling, e.g. 'Mohammadpur' for মোহাম্মদপুর. "
            "Call search_offers again with the English spelling."
        )
    parsed_type = _parse_offer_type(offer_type) if offer_type else None

    shown = userdata.shown_listings
    property_id = None
    card = None
    if listing_number is not None:
        card = shown.get(listing_number)
        if card is None:
            raise ToolError(
                f"No listing #{listing_number} has been shown in this conversation. "
                "Use a #number from search_apartments, or leave listing_number out."
            )
        if card.get("listing_type") != "sale":
            return (
                f"#{listing_number} {card['title']} is for rent. Offers apply to sale listings "
                "only, so there are none on it. Don't offer the customer any discount on it, and "
                "don't bring offers up; if they asked whether the rent is negotiable, point them "
                "to the team's phone and head office, as WHAT YOU KNOW says."
            )
        property_id = uuid.UUID(card["id"])

    db = SessionLocal()
    try:
        offers = offer_repo.list_live(
            db,
            property_id=property_id,
            location=location,
            offer_type=parsed_type,
            limit=_MAX_OFFERS,
        )
        lines = []
        for offer in offers:
            line = f"- {offer_repo.describe(offer)}"
            if offer.applies_to_all_sale:
                line += "; on every listing for sale"
            else:
                listings = offer_repo.live_listings(offer, _MAX_LISTINGS_PER_OFFER + 1)
                refs = [
                    _listing_ref(shown, p.id, p.title, p.neighborhood or p.city)
                    for p in listings[:_MAX_LISTINGS_PER_OFFER]
                ]
                more = " and more" if len(listings) > _MAX_LISTINGS_PER_OFFER else ""
                line += f"; on {', '.join(refs)}{more}"
            if offer.ends_on:
                line += f"; until {offer.ends_on.isoformat()}"
            if offer.description:
                line += f". {offer.description.strip()}"
            if offer.terms:
                line += f" Terms: {offer.terms.strip()}"
            lines.append(line)
    finally:
        db.close()

    if not lines:
        scope = (
            f"on #{listing_number} {card['title']}"
            if card
            else f"in {location}" if location else "right now"
        )
        return (
            f"No current offers {scope}. Don't suggest any discount, and don't say the price "
            "is fixed or negotiable or that you can't confirm it: for pricing beyond this, point "
            "the customer to the team's phone and head office, as WHAT YOU KNOW says."
        )
    return f"Current offers ({len(lines)}):\n" + "\n".join(lines) + "\n" + _GUARDRAIL
