"""Admin offer CRUD (/api/offers) and the live-offer rules in offer_repo."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.db.session import SessionLocal
from app.repositories import offer_repo
from offer_helpers import PREFIX, cleanup, make_property, offer_payload, set_property


@pytest.fixture
def props():
    cleanup()
    yield {
        "sale": make_property("sale flat"),
        "sale2": make_property("second sale flat"),
        "rent": make_property("rent flat", listing_type="rent"),
        "inactive": make_property("inactive sale flat", is_active=False),
    }
    cleanup()


def _live_ids(**filters) -> set[str]:
    db = SessionLocal()
    try:
        return {str(o.id) for o in offer_repo.list_live(db, limit=500, **filters)}
    finally:
        db.close()


def _live_for(property_id) -> set[str]:
    db = SessionLocal()
    try:
        return {str(o.id) for o in offer_repo.live_for_properties(db, [property_id])[property_id]}
    finally:
        db.close()


# ---- auth ----


def test_offers_need_auth(anon_api):
    assert anon_api.get("/api/offers").status_code == 401
    assert anon_api.post("/api/offers", json=offer_payload("x")).status_code == 401


# ---- CRUD ----


def test_crud(api, props):
    created = api.post(
        "/api/offers", json=offer_payload("crud", property_ids=[str(props["sale"])])
    )
    assert created.status_code == 201, created.text
    offer = created.json()
    assert offer["property_ids"] == [str(props["sale"])]
    assert offer["properties"][0]["title"] == f"{PREFIX} sale flat"
    assert offer["discount_amount"] == 500_000
    assert offer["is_active"] is True

    oid = offer["id"]
    assert api.get(f"/api/offers/{oid}").json()["title"] == offer["title"]
    assert oid in {o["id"] for o in api.get("/api/offers").json()}

    patched = api.patch(
        f"/api/offers/{oid}",
        json={"title": f"{PREFIX} renamed", "property_ids": [str(props["sale2"])]},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["title"] == f"{PREFIX} renamed"
    assert patched.json()["property_ids"] == [str(props["sale2"])]
    # Fields not sent are kept.
    assert patched.json()["discount_amount"] == 500_000

    assert api.delete(f"/api/offers/{oid}").status_code == 204
    assert api.get(f"/api/offers/{oid}").status_code == 404


@pytest.mark.parametrize(
    "overrides",
    [
        {"offer_type": "percent_discount", "discount_amount": None},
        {"offer_type": "single_payment_discount", "discount_amount": None},
        {"offer_type": "flat_discount", "discount_amount": None},
        {"offer_type": "percent_discount", "discount_percent": 150},
        {"starts_on": "2026-11-10", "ends_on": "2026-11-09"},
    ],
)
def test_invalid_offer_is_rejected(api, overrides):
    response = api.post("/api/offers", json=offer_payload("invalid", **overrides))
    assert response.status_code == 422, response.text


def test_patch_is_validated_as_a_whole(api, props):
    oid = api.post("/api/offers", json=offer_payload("whole")).json()["id"]
    # Switching to a percent discount without a percent leaves an invalid offer.
    response = api.patch(f"/api/offers/{oid}", json={"offer_type": "percent_discount"})
    assert response.status_code == 422, response.text
    ok = api.patch(
        f"/api/offers/{oid}", json={"offer_type": "percent_discount", "discount_percent": 12.5}
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["discount_percent"] == 12.5


@pytest.mark.parametrize("which", ["rent", "inactive"])
def test_only_active_sale_listings_can_be_linked(api, props, which):
    response = api.post(
        "/api/offers", json=offer_payload("bad link", property_ids=[str(props[which])])
    )
    assert response.status_code == 422, response.text
    assert "sale listings only" in response.text

    oid = api.post("/api/offers", json=offer_payload("good link")).json()["id"]
    response = api.patch(f"/api/offers/{oid}", json={"property_ids": [str(props[which])]})
    assert response.status_code == 422, response.text


def test_all_sale_toggle_clears_property_ids(api, props):
    created = api.post(
        "/api/offers",
        json=offer_payload(
            "all sale", applies_to_all_sale=True, property_ids=[str(props["sale"])]
        ),
    ).json()
    assert created["applies_to_all_sale"] is True
    assert created["property_ids"] == []

    linked = api.post(
        "/api/offers", json=offer_payload("linked", property_ids=[str(props["sale"])])
    ).json()
    toggled = api.patch(f"/api/offers/{linked['id']}", json={"applies_to_all_sale": True}).json()
    assert toggled["property_ids"] == []

    # An all-sale offer reaches every active sale listing, and no rental.
    assert created["id"] in _live_for(props["sale2"])
    assert created["id"] not in _live_for(props["rent"])
    assert created["id"] not in _live_for(props["inactive"])


# ---- live offers ----


def _dhaka_today():
    return datetime.now(ZoneInfo("Asia/Dhaka")).date()


def test_date_window(api, props):
    today = _dhaka_today()
    day = timedelta(days=1)
    windows = {
        "today only": (today, today),
        "open-ended": (None, None),
        "starts tomorrow": (today + day, None),
        "ended yesterday": (None, today - day),
    }
    ids = {}
    for name, (starts, ends) in windows.items():
        ids[name] = api.post(
            "/api/offers",
            json=offer_payload(
                name,
                property_ids=[str(props["sale"])],
                starts_on=starts.isoformat() if starts else None,
                ends_on=ends.isoformat() if ends else None,
            ),
        ).json()["id"]
    inactive = api.post(
        "/api/offers",
        json=offer_payload("switched off", property_ids=[str(props["sale"])], is_active=False),
    ).json()["id"]

    live = _live_ids(property_id=props["sale"])
    assert ids["today only"] in live
    assert ids["open-ended"] in live
    assert ids["starts tomorrow"] not in live
    assert ids["ended yesterday"] not in live
    assert inactive not in live
    assert _live_for(props["sale"]) >= {ids["today only"], ids["open-ended"]}
    assert not _live_for(props["sale"]) & {ids["starts tomorrow"], ids["ended yesterday"], inactive}


def test_today_is_the_agency_timezone(api, props, monkeypatch):
    """UTC+14 and UTC-12 are always on different calendar days: an offer that
    starts on the UTC+14 date is live there and not yet live at UTC-12."""
    ahead, behind = ZoneInfo("Pacific/Kiritimati"), ZoneInfo("Etc/GMT+12")
    starts = datetime.now(ahead).date()
    assert starts != datetime.now(behind).date()
    oid = api.post(
        "/api/offers",
        json=offer_payload(
            "tz", property_ids=[str(props["sale"])], starts_on=starts.isoformat()
        ),
    ).json()["id"]

    monkeypatch.setattr(offer_repo, "agency_tz", lambda: ahead)
    assert oid in _live_ids(property_id=props["sale"])
    monkeypatch.setattr(offer_repo, "agency_tz", lambda: behind)
    assert oid not in _live_ids(property_id=props["sale"])
    assert oid not in _live_for(props["sale"])


def test_listing_switched_to_rent_drops_out(api, props):
    oid = api.post(
        "/api/offers", json=offer_payload("rent switch", property_ids=[str(props["sale"])])
    ).json()["id"]
    assert oid in _live_ids(property_id=props["sale"])
    assert oid in {o["id"] for o in api.get("/api/public/offers").json()}

    set_property(props["sale"], listing_type="rent")

    assert oid not in _live_ids()
    assert _live_for(props["sale"]) == set()
    assert oid not in {o["id"] for o in api.get("/api/public/offers").json()}
    # Still linked in the dashboard, so switching back restores it.
    assert api.get(f"/api/offers/{oid}").json()["property_ids"] == [str(props["sale"])]
    set_property(props["sale"], listing_type="sale")
    assert oid in _live_ids(property_id=props["sale"])


def test_deactivated_listing_drops_out(api, props):
    oid = api.post(
        "/api/offers", json=offer_payload("deactivate", property_ids=[str(props["sale"])])
    ).json()["id"]
    set_property(props["sale"], is_active=False)
    assert oid not in _live_ids()


def test_location_and_type_filters(api, props):
    oid = api.post(
        "/api/offers", json=offer_payload("filters", property_ids=[str(props["sale"])])
    ).json()["id"]
    assert oid in _live_ids(location="Pytestpur")
    assert oid in _live_ids(neighborhood="Pytestpur")
    assert oid not in _live_ids(location="Gulshan")
    assert oid in _live_ids(location="Pytestpur", offer_type=offer_repo.OfferType.flat_discount)
    assert oid not in _live_ids(
        location="Pytestpur", offer_type=offer_repo.OfferType.fee_waiver
    )


def test_patch_error_with_dates_is_json(api, props):
    oid = api.post(
        "/api/offers",
        json=offer_payload("dated", starts_on="2026-11-01", ends_on="2026-11-30"),
    ).json()["id"]
    response = api.patch(f"/api/offers/{oid}", json={"ends_on": "2026-10-01"})
    assert response.status_code == 422
    assert "ends_on must be on or after starts_on" in response.text
