import uuid

import pytest
from sqlalchemy import text

from app.api.routes_public import MAX_PUBLIC_LISTINGS
from app.db.session import SessionLocal
from app.repositories import agent_config_repo, offer_repo, property_repo
from app.services import agent_config_service

_HIDDEN_FIELDS = {"address_line", "is_active", "created_at", "updated_at"}


def test_public_listings_need_no_auth(anon_api):
    response = anon_api.get("/api/public/listings")
    assert response.status_code == 200, response.text
    listings = response.json()
    assert 0 < len(listings) <= 6
    assert all(listing["is_featured"] for listing in listings)


def test_public_listings_hide_internal_fields(anon_api):
    listings = anon_api.get("/api/public/listings", params={"limit": 24}).json()
    assert listings
    for listing in listings:
        assert not _HIDDEN_FIELDS & listing.keys()
        assert listing["image_url"]
        assert listing["images"]


def test_public_listings_limit_is_capped(anon_api):
    listings = anon_api.get(
        "/api/public/listings", params={"limit": 500, "featured": "false"}
    ).json()
    assert len(listings) == MAX_PUBLIC_LISTINGS


# ---- one listing (the property page) ----

_INACTIVE_TITLE = "PYTEST-PUBLIC inactive"


@pytest.fixture
def inactive_listing():
    db = SessionLocal()
    try:
        prop = property_repo.create(
            db,
            {
                "title": _INACTIVE_TITLE,
                "address_line": "Road 1, Testpur",
                "city": "Dhaka",
                "neighborhood": "Testpur",
                "property_type": "apartment",
                "listing_type": "rent",
                "price": 25000,
                "bedrooms": 2,
                "bathrooms": 1,
                "is_active": False,
            },
        )
        yield prop.id
    finally:
        db.execute(text("delete from properties where title = :t"), {"t": _INACTIVE_TITLE})
        db.commit()
        db.close()


def test_public_listing_detail(anon_api):
    listing = anon_api.get("/api/public/listings").json()[0]
    response = anon_api.get(f"/api/public/listings/{listing['id']}")
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["id"] == listing["id"]
    assert detail["title"] == listing["title"]
    assert not _HIDDEN_FIELDS & detail.keys()
    assert {"description", "images", "amenities", "available_from"} <= detail.keys()


def test_public_listing_detail_hides_inactive(anon_api, inactive_listing):
    response = anon_api.get(f"/api/public/listings/{inactive_listing}")
    assert response.status_code == 404


def test_public_listing_detail_unknown_id(anon_api):
    response = anon_api.get(f"/api/public/listings/{uuid.uuid4()}")
    assert response.status_code == 404


@pytest.mark.parametrize("bad_id", ["not-a-uuid", "123"])
def test_public_listing_detail_malformed_id_is_404(anon_api, bad_id):
    response = anon_api.get(f"/api/public/listings/{bad_id}")
    assert response.status_code == 404


def test_agent_info(anon_api):
    response = anon_api.get("/api/public/agent-info")
    assert response.status_code == 200, response.text
    info = response.json()
    assert set(info) == {"assistant_name", "agency_name"}
    db = SessionLocal()
    try:
        expected = agent_config_service.resolve(agent_config_repo.get(db))
    finally:
        db.close()
    assert info == {
        "assistant_name": expected.assistant_name,
        "agency_name": expected.agency_name,
    }


# ---- offers ----


@pytest.fixture
def offered_listing():
    from offer_helpers import PREFIX, cleanup, make_property

    cleanup()
    sale = make_property("public sale flat")
    rent = make_property("public rent flat", listing_type="rent")
    db = SessionLocal()
    try:
        offer = offer_repo.create(
            db,
            {
                "title": f"{PREFIX} public 8% off",
                "offer_type": "percent_discount",
                "discount_percent": 8,
                "terms": "Booking money within 7 days.",
                "property_ids": [sale],
            },
        )
        offer_id = str(offer.id)
    finally:
        db.close()
    yield {"sale": str(sale), "rent": str(rent), "offer_id": offer_id}
    cleanup()


def test_listing_detail_has_offers(anon_api, offered_listing):
    detail = anon_api.get(f"/api/public/listings/{offered_listing['sale']}").json()
    badge = next(o for o in detail["offers"] if o["id"] == offered_listing["offer_id"])
    assert badge["offer_type"] == "percent_discount"
    assert badge["discount_percent"] == 8
    assert set(badge) == {
        "id", "title", "offer_type", "discount_percent", "discount_amount", "ends_on",
    }  # fmt: skip
    rent = anon_api.get(f"/api/public/listings/{offered_listing['rent']}").json()
    assert rent["offers"] == []


def test_listing_list_has_offers_key(anon_api):
    listings = anon_api.get("/api/public/listings", params={"limit": 24, "featured": "false"})
    for listing in listings.json():
        assert isinstance(listing["offers"], list)
        if listing["listing_type"] == "rent":
            assert listing["offers"] == []


def test_public_offers(anon_api, offered_listing):
    response = anon_api.get("/api/public/offers")
    assert response.status_code == 200, response.text
    offer = next(o for o in response.json() if o["id"] == offered_listing["offer_id"])
    assert "is_active" not in offer and "created_at" not in offer
    assert offer["terms"] == "Booking money within 7 days."
    assert [l["id"] for l in offer["listings"]] == [offered_listing["sale"]]
    assert not {"address_line", "is_active"} & offer["listings"][0].keys()
    for o in response.json():
        assert len(o["listings"]) <= 6
        if o["applies_to_all_sale"]:
            assert o["listings"] == []


# ---- browse (the "all properties" page) ----

_BROWSE = "/api/public/listings/browse"


def _browse(api, **params) -> dict:
    response = api.get(_BROWSE, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_browse_needs_no_auth_and_pages_every_active_listing(anon_api):
    first = _browse(anon_api, limit=48)
    assert set(first) == {"items", "total", "limit", "offset"}
    total = first["total"]
    # Not just the featured ones: the seed holds 100+ active listings.
    assert total > MAX_PUBLIC_LISTINGS
    db = SessionLocal()
    try:
        active = db.scalar(text("select count(*) from properties where is_active"))
    finally:
        db.close()
    assert total == active

    seen: list[str] = []
    for offset in range(0, total, 48):
        page = _browse(anon_api, limit=48, offset=offset)
        assert page["total"] == total
        seen += [item["id"] for item in page["items"]]
    assert len(seen) == len(set(seen)) == total
    for item in first["items"]:
        assert not _HIDDEN_FIELDS & item.keys()
        assert isinstance(item["offers"], list)


def test_browse_default_sort_puts_featured_first(anon_api):
    items = _browse(anon_api, limit=48)["items"]
    flags = [item["is_featured"] for item in items]
    assert flags == sorted(flags, reverse=True)


@pytest.mark.parametrize("sort", ["price_asc", "price_desc"])
def test_browse_sorts_by_price(anon_api, sort):
    prices = [item["price"] for item in _browse(anon_api, sort=sort, limit=48)["items"]]
    assert prices == sorted(prices, reverse=sort == "price_desc")


def test_browse_filters(anon_api):
    rent = _browse(anon_api, listing_type="rent", limit=48)
    assert rent["total"] > 0
    assert all(item["listing_type"] == "rent" for item in rent["items"])

    types = _browse(anon_api, property_type=["apartment", "duplex"], limit=48)
    assert types["total"] > 0
    assert {item["property_type"] for item in types["items"]} <= {"apartment", "duplex"}

    priced = _browse(anon_api, listing_type="sale", min_price=5_000_000, max_price=20_000_000)
    assert priced["total"] > 0
    assert all(5_000_000 <= item["price"] <= 20_000_000 for item in priced["items"])

    roomy = _browse(anon_api, min_bedrooms=3, min_bathrooms=2, limit=48)
    assert roomy["total"] > 0
    assert all(i["bedrooms"] >= 3 and i["bathrooms"] >= 2 for i in roomy["items"])


def test_browse_area_matches_city_or_neighborhood(anon_api):
    facets = anon_api.get("/api/public/listings/facets").json()
    hood = facets["neighborhoods"][0]
    by_hood = _browse(anon_api, area=hood["name"].upper(), limit=48)
    assert by_hood["total"] >= hood["count"]
    assert all(
        hood["name"] in (item["neighborhood"], item["city"]) for item in by_hood["items"]
    )
    city = facets["cities"][0]
    by_city = _browse(anon_api, area=city["name"], limit=48)
    assert by_city["total"] >= city["count"]
    assert all(city["name"] in (i["city"], i["neighborhood"]) for i in by_city["items"])


def test_browse_no_matches_is_an_empty_page(anon_api):
    page = _browse(anon_api, area="Nowhere-in-particular")
    assert page["items"] == [] and page["total"] == 0


@pytest.mark.parametrize(
    "params",
    [{"limit": 49}, {"limit": 0}, {"offset": -1}, {"sort": "random"}, {"property_type": "castle"}],
)
def test_browse_rejects_bad_params(anon_api, params):
    assert anon_api.get(_BROWSE, params=params).status_code == 422


def test_browse_hides_inactive(anon_api, inactive_listing):
    page = _browse(anon_api, area="Testpur")
    assert page["total"] == 0


def test_browse_items_carry_offers(anon_api, offered_listing):
    from offer_helpers import AREA

    page = _browse(anon_api, area=AREA)
    by_id = {item["id"]: item for item in page["items"]}
    assert page["total"] == 2
    sale_offers = by_id[offered_listing["sale"]]["offers"]
    # Seeded "all sale listings" offers may apply too.
    assert offered_listing["offer_id"] in [o["id"] for o in sale_offers]
    assert by_id[offered_listing["rent"]]["offers"] == []


def test_listing_facets(anon_api):
    response = anon_api.get("/api/public/listings/facets")
    assert response.status_code == 200, response.text
    facets = response.json()
    assert facets["total"] == _browse(anon_api)["total"]
    assert sum(c["count"] for c in facets["cities"]) == facets["total"]
    assert sum(t["count"] for t in facets["property_types"]) == facets["total"]
    assert {"name", "city", "count"} == set(facets["neighborhoods"][0])
    ranges = {r["listing_type"]: r for r in facets["price_ranges"]}
    assert set(ranges) == {"rent", "sale"}
    for listing_type, bounds in ranges.items():
        cheapest = _browse(anon_api, listing_type=listing_type, sort="price_asc", limit=1)
        assert cheapest["items"][0]["price"] == bounds["min"]
        assert cheapest["total"] == bounds["count"]
    assert facets["max_bedrooms"] >= 1
