import asyncio
from types import SimpleNamespace

import pytest
from livekit.agents.llm import ToolError
from sqlalchemy import select, text

from app.agent.tools.search_apartments import _parse_property_type, search_apartments
from app.agent.userdata import Channel, SessionUserdata
from app.data import seed_properties
from app.db.session import SessionLocal
from app.models.property import Property, PropertyType
from app.repositories import property_repo

TITLE_PREFIX = "PYTEST-TYPES"


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    db = SessionLocal()
    try:
        db.execute(text("delete from properties where title like :p"), {"p": f"{TITLE_PREFIX}%"})
        db.commit()
    finally:
        db.close()


async def _no_op_send_text(*args, **kwargs):
    return None


def _search(**criteria) -> str:
    room = SimpleNamespace(local_participant=SimpleNamespace(send_text=_no_op_send_text))
    ctx = SimpleNamespace(userdata=SessionUserdata(channel=Channel.inbound_chat, room=room))
    return asyncio.run(search_apartments(ctx, **criteria))


def _payload(property_type: str, **overrides) -> dict:
    return {
        "title": f"{TITLE_PREFIX} {property_type}",
        "address_line": "Road 1, Testpur",
        "city": "Dhaka",
        "neighborhood": "Testpur",
        "property_type": property_type,
        "listing_type": "sale",
        "price": 1000000,
        "bedrooms": 0,
        "bathrooms": 0,
        "images": ["https://example.invalid/a.jpg", "https://example.invalid/b.jpg"],
        **overrides,
    }


@pytest.mark.parametrize("value", ["duplex", "studio", "commercial", "plot"])
def test_new_property_types_round_trip(api, value):
    created = api.post("/api/properties", json=_payload(value))
    assert created.status_code == 201, created.text
    assert created.json()["property_type"] == value

    db = SessionLocal()
    try:
        prop = db.scalar(select(Property).where(Property.title == f"{TITLE_PREFIX} {value}"))
        assert prop.property_type == PropertyType(value)
        assert prop.images == ["https://example.invalid/a.jpg", "https://example.invalid/b.jpg"]
        assert prop.is_featured is False
    finally:
        db.close()


def test_patch_and_soft_delete(api):
    prop_id = api.post("/api/properties", json=_payload("duplex")).json()["id"]

    patched = api.patch(f"/api/properties/{prop_id}", json={"price": 2500000, "images": None})
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["price"] == 2500000
    assert body["images"] is None
    assert body["title"] == f"{TITLE_PREFIX} duplex"  # untouched fields stay

    assert api.patch(f"/api/properties/{prop_id}", json={"title": None}).json()["title"] == (
        f"{TITLE_PREFIX} duplex"
    )  # a null for a required field is ignored, not written

    assert api.delete(f"/api/properties/{prop_id}").status_code == 204
    listed = {p["id"]: p for p in api.get("/api/properties", params={"limit": 1000}).json()}
    assert listed[prop_id]["is_active"] is False


def test_unknown_property_404(api):
    missing = "00000000-0000-0000-0000-000000000000"
    assert api.patch(f"/api/properties/{missing}", json={"price": 1}).status_code == 404
    assert api.delete(f"/api/properties/{missing}").status_code == 404


def test_property_routes_require_auth(anon_api):
    missing = "00000000-0000-0000-0000-000000000000"
    assert anon_api.get("/api/properties").status_code == 401
    assert anon_api.patch(f"/api/properties/{missing}", json={}).status_code == 401
    assert anon_api.delete(f"/api/properties/{missing}").status_code == 401


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("flat", PropertyType.apartment),
        ("Apartment", PropertyType.apartment),
        ("house", PropertyType.apartment),
        ("home", PropertyType.apartment),
        ("villa", PropertyType.duplex),
        ("shop", PropertyType.commercial),
        ("Office Space", PropertyType.commercial),
        ("land", PropertyType.plot),
        ("duplex", PropertyType.duplex),
        ("Penthouse", PropertyType.duplex),
        ("commercial", PropertyType.commercial),
        ("plot", PropertyType.plot),
    ],
)
def test_parse_property_type_synonyms(raw, expected):
    assert _parse_property_type(raw) == expected


def test_flat_search_no_longer_errors():
    assert _search(location="Gulshan", property_type="flat").startswith("Found")


def test_land_search_finds_plots():
    result = _search(location="Purbachal", property_type="land")
    assert result.startswith("Found")
    assert "Plot" in result


def test_generic_search_excludes_commercial_and_plots():
    db = SessionLocal()
    try:
        results = property_repo.search(db, location="Gulshan", limit=1000)
        assert results
        assert not {p.property_type for p in results} & {PropertyType.commercial, PropertyType.plot}
        # ...but asking for them explicitly still finds them.
        assert property_repo.search(db, location="Gulshan", property_type=PropertyType.commercial)
    finally:
        db.close()


def test_seed_titles_unique():
    titles = [p["title"] for p in seed_properties.ALL_PROPERTIES]
    assert len(titles) == len(set(titles))


def test_seed_featured_listings_have_galleries():
    featured = seed_properties.FEATURED_PROPERTIES
    assert len(featured) >= 20
    for data in featured:
        assert data["is_featured"] is True
        assert data["image_url"] == data["images"][0]
        assert 3 <= len(data["images"]) <= 5
        if data["property_type"] == PropertyType.plot:
            assert data["bedrooms"] == 0 and data["bathrooms"] == 0
    for data in seed_properties.SAMPLE_PROPERTIES:
        assert "placehold.co" not in data["image_url"]


def test_seed_upsert_is_idempotent_and_keeps_admin_edits():
    template = seed_properties.FEATURED_PROPERTIES[0]
    db = SessionLocal()
    try:
        seed_properties.seed(db)  # make sure every seed row exists first
        assert seed_properties.seed(db) == 0

        prop = db.scalar(select(Property).where(Property.title == template["title"]))
        original = (prop.price, prop.is_active, prop.images, prop.image_url)
        try:
            prop.price = 123
            prop.is_active = False
            prop.images = None
            prop.image_url = "https://placehold.co/600x400?text=Old"
            db.commit()

            assert seed_properties.seed(db) == 0
            db.refresh(prop)
            assert float(prop.price) == 123
            assert prop.is_active is False
            assert prop.images == template["images"]
            assert prop.image_url == template["image_url"]
        finally:
            prop.price, prop.is_active, prop.images, prop.image_url = original
            db.commit()
    finally:
        db.close()


@pytest.mark.parametrize("location", ["মোহাম্মদপুর", "মোহাম্মদপুর, ঢাকা"])
def test_bangla_script_location_asks_for_english_spelling(location):
    # Listings are stored in English; a Bangla-script location matches nothing,
    # so the LLM must retry with the English spelling instead of reporting "none".
    with pytest.raises(ToolError, match="English"):
        _search(location=location)


def test_english_location_still_searches():
    assert _search(location="Mohammadpur, Dhaka", listing_type="rent").startswith("Found")


@pytest.mark.parametrize("value", ["house", "townhouse", "penthouse"])
def test_removed_types_are_gone_from_the_enum(value):
    assert value not in {t.value for t in PropertyType}
