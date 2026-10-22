"""search_offers (the agent tool) and the offers search_apartments puts on its cards."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from livekit.agents.llm import ToolError

from app.agent.tools.search_apartments import search_apartments
from app.agent.tools.search_offers import search_offers
from app.agent.userdata import Channel, SessionUserdata
from app.db.session import SessionLocal
from app.repositories import offer_repo
from offer_helpers import AREA, PREFIX, cleanup, make_property


def _ctx():
    sent: list[tuple[str, str]] = []

    async def send_text(text, topic):
        sent.append((topic, text))

    room = SimpleNamespace(local_participant=SimpleNamespace(send_text=send_text))
    ctx = SimpleNamespace(userdata=SessionUserdata(channel=Channel.inbound_chat, room=room))
    ctx.sent = sent
    return ctx


def _offers(ctx=None, **kwargs) -> str:
    return asyncio.run(search_offers(ctx or _ctx(), **kwargs))


def _apartments(ctx, **kwargs) -> str:
    return asyncio.run(search_apartments(ctx, **kwargs))


@pytest.fixture
def setup():
    cleanup()
    sale = make_property("tool sale flat")
    rent = make_property("tool rent flat", listing_type="rent")
    db = SessionLocal()
    try:
        offer = offer_repo.create(
            db,
            {
                "title": f"{PREFIX} Tk 7 lakh off",
                "offer_type": "flat_discount",
                "discount_amount": 700_000,
                "terms": "Book by month end.",
                "property_ids": [sale],
            },
        )
        offer_id = str(offer.id)
    finally:
        db.close()
    yield SimpleNamespace(sale=sale, rent=rent, offer_id=offer_id)
    cleanup()


def _show(ctx, setup) -> dict[str, int]:
    """Runs a search over the test area; returns listing number by property id."""
    _apartments(ctx, location=AREA)
    return {card["id"]: n for n, card in ctx.userdata.shown_listings.items()}


def test_cards_carry_live_offers(setup):
    ctx = _ctx()
    text = _apartments(ctx, location=AREA)
    topic, payload = ctx.sent[-1]
    assert topic == "apartment-shortlist"
    cards = {c["id"]: c for c in json.loads(payload)}
    sale_offers = cards[str(setup.sale)]["offers"]
    assert setup.offer_id in {o["id"] for o in sale_offers}
    badge = next(o for o in sale_offers if o["id"] == setup.offer_id)
    assert badge["offer_type"] == "flat_discount"
    assert badge["discount_amount"] == 700_000
    assert cards[str(setup.rent)]["offers"] == []
    assert f"has offer: {PREFIX} Tk 7 lakh off (flat discount, 7 lakh taka off)" in text
    assert "never invent or negotiate a discount" in text


def test_offers_for_a_shown_listing(setup):
    ctx = _ctx()
    numbers = _show(ctx, setup)
    n = numbers[str(setup.sale)]
    text = _offers(ctx, listing_number=n)
    assert f"{PREFIX} Tk 7 lakh off" in text
    assert f"#{n} {PREFIX} tool sale flat ({AREA})" in text
    assert "Terms: Book by month end." in text
    assert "Never invent, combine, estimate or negotiate a discount" in text


def test_rent_listing_has_no_offers(setup):
    ctx = _ctx()
    numbers = _show(ctx, setup)
    text = _offers(ctx, listing_number=numbers[str(setup.rent)])
    assert "is for rent" in text
    assert PREFIX + " Tk 7 lakh off" not in text


def test_offers_by_location_and_type(setup):
    assert f"{PREFIX} Tk 7 lakh off" in _offers(location=AREA)
    assert f"{PREFIX} Tk 7 lakh off" in _offers(location=AREA, offer_type="flat discount")
    assert f"{PREFIX} Tk 7 lakh off" not in _offers(location=AREA, offer_type="fee_waiver")


def test_no_offers_says_so():
    text = _offers(location="Nowhereville")
    assert text.startswith("No current offers in Nowhereville")
    assert "Don't suggest any discount" in text
    # Pricing beyond the offers goes to the team, never "I can't confirm".
    assert "head office" in text
    assert "team can discuss pricing at a viewing" not in text


@pytest.mark.parametrize(
    "kwargs",
    [
        {"listing_number": 99},
        {"location": "মোহাম্মদপুর"},
        {"offer_type": "buy one get one"},
    ],
)
def test_bad_arguments_are_tool_errors(kwargs):
    with pytest.raises(ToolError):
        _offers(**kwargs)
