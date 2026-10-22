import asyncio
import re
from types import SimpleNamespace

import pytest

from app.agent.tools.search_apartments import search_apartments
from app.agent.userdata import Channel, SessionUserdata
from app.db.session import SessionLocal
from app.repositories import property_repo


async def _no_op_send_text(*args, **kwargs):
    return None


def _ctx() -> SimpleNamespace:
    room = SimpleNamespace(local_participant=SimpleNamespace(send_text=_no_op_send_text))
    return SimpleNamespace(userdata=SessionUserdata(channel=Channel.inbound_chat, room=room))


def _search(ctx=None, **criteria) -> str:
    return asyncio.run(search_apartments(ctx or _ctx(), **criteria))


@pytest.mark.parametrize("location", ["Mirpur 10", "Baridhara DOHS"])
def test_sub_area_matches_address(location):
    db = SessionLocal()
    try:
        assert property_repo.search(db, location=location)
    finally:
        db.close()


def test_generator_synonym_matches_generator_backup():
    result = _search(amenities=["generator"])
    assert "No listings record" not in result
    assert "generator_backup" in result


def test_unknown_amenity_flagged():
    result = _search(location="Mohammadpur", amenities=["pet_friendly"])
    assert result.startswith("No listings record 'pet_friendly'")
    # A missing listing detail gets a viewing, not the head-office number.
    assert "head office" not in result
    assert "viewing" in result
    assert "Tell the customer you can't confirm" not in result


def test_amenity_nothing_has_is_dropped_before_area_or_budget():
    result = _search(location="Keraniganj", amenities=["gym"])
    assert result.startswith("Nothing matched with 'gym', so the search dropped it.")
    assert "Found " in result


def test_only_the_amenity_nothing_has_is_dropped():
    # Keraniganj has lift homes but no gym: gym goes, lift stays.
    result = _search(location="Keraniganj", amenities=["gym", "lift"])
    assert result.startswith("Nothing matched with 'gym', so")
    assert "'lift'" not in result.split("Found ")[0]
    listings = [line for line in result.splitlines() if line.startswith("#")]
    assert listings and all("lift" in line for line in listings)


def test_amenity_that_matches_is_kept():
    result = _search(amenities=["gym"])
    assert "Nothing matched with" not in result
    assert "gym" in result


def test_listing_number_stable_across_searches():
    ctx = _ctx()
    _search(ctx, location="Uttara")
    first = dict(ctx.userdata.shown_listings)
    _search(ctx, location="Gulshan")
    result = _search(ctx, location="Uttara")
    for number, card in first.items():
        assert ctx.userdata.shown_listings[number]["id"] == card["id"]
        assert f"#{number} {card['title']}" in result


# --- sectors and their neighbours -------------------------------------------------


def _addresses(location, **criteria):
    db = SessionLocal()
    try:
        return [p.address_line for p in property_repo.search(db, location=location, limit=100, **criteria)]
    finally:
        db.close()


def test_mirpur_1_is_not_mirpur_10_to_14():
    addresses = _addresses("Mirpur 1")
    assert addresses
    for address in addresses:
        assert not re.search(r"(Mirpur|Section) 1\d", address), address


def test_uttara_sector_4_excludes_purbachal_sector_4():
    addresses = _addresses("Uttara Sector 4")
    assert addresses
    assert all("Purbachal" not in a for a in addresses)


def test_whole_area_includes_its_named_pockets():
    assert any("Lalmatia" in a for a in _addresses("Mohammadpur"))


def test_sector_with_matches_shows_only_that_sector():
    # "Tell me about the Mirpur 11 flat": the cards hold Mirpur 11 alone, no
    # neighbours padding the list.
    ctx = _ctx()
    result = _search(ctx, location="Mirpur 11", listing_type="sale")
    assert "(nearby" not in result
    assert "itself" not in result
    lines = [line for line in result.splitlines() if line.startswith("#")]
    assert lines and all("area: Mirpur 11" in line for line in lines)


def test_empty_sector_falls_back_to_neighbours():
    ctx = _ctx()
    result = _search(ctx, location="Mirpur 10", listing_type="rent", budget_max=15000)
    lines = [line for line in result.splitlines() if line.startswith("#")]
    assert lines and "(nearby" in lines[0]
    # Besides the neighbours, at most the one Mirpur 10 home just past the budget.
    own = [line for line in lines if "(nearby" not in line]
    assert len(own) <= 1 and all("area: Mirpur 10" in line for line in own)
    ids = [card["id"] for card in ctx.userdata.shown_listings.values()]
    assert len(ids) == len(set(ids))


def test_in_budget_neighbours_beat_the_out_of_budget_fallback():
    # Nothing in Mirpur 10 rents under 17,000, but Kazipara next door does.
    result = _search(location="Mirpur 10", listing_type="rent", budget_max=17000)
    assert "Kazipara (nearby, not Mirpur 10)" in result
    assert "Nothing in Mirpur 10 matched" not in result


def test_impossible_budget_gives_the_sector_price_range():
    result = _search(location="Mirpur 12", listing_type="rent", budget_max=100)
    assert "Nothing in Mirpur 12 matched" in result
    assert "(nearby" not in result


def test_bengali_digits_in_location_are_accepted():
    result = _search(location="Mirpur ১২", listing_type="sale")
    assert "English spelling" not in result
    assert "Mirpur 12" in result


def test_phone_header_also_splits_sector_and_nearby():
    ctx = _ctx()
    ctx.userdata.is_phone_call = True
    result = _search(ctx, location="Mirpur 10", listing_type="rent", budget_max=15000)
    assert "in Mirpur 10 itself" in result
    assert "This is a phone call" in result


# --- budget band, house/flat, rent/sale and several areas ---------------------------


def _prices(result: str) -> list[int]:
    lines = [line for line in result.splitlines() if line.startswith("#")]
    return [int(re.search(r"— ([\d,]+) taka", line).group(1).replace(",", "")) for line in lines]


def test_budget_ranks_around_it_with_one_home_just_past():
    prices = _prices(_search(listing_type="rent", property_type="apartment", budget_max=15000))
    assert len(prices) == 5
    over = [p for p in prices if p > 15000]
    assert len(over) == 1 and over[0] <= 16500
    # Closest to 15,000 first, not the 7,000 flats.
    assert min(prices) > 7000


def test_strict_maximum_is_never_crossed():
    result = _search(
        listing_type="rent", property_type="apartment", budget_max=15000, budget_max_strict=True
    )
    prices = _prices(result)
    assert prices and all(p <= 15000 for p in prices)


def test_strict_minimum_is_never_crossed():
    prices = _prices(
        _search(listing_type="rent", budget_min=10000, budget_min_strict=True, budget_max=15000)
    )
    assert prices and all(p >= 10000 for p in prices)
    assert sum(p > 15000 for p in prices) <= 1


def test_more_shows_new_homes_inside_the_band():
    ctx = _ctx()
    _search(ctx, listing_type="rent", property_type="apartment", budget_max=15000)
    first = {card["id"] for card in ctx.userdata.shown_listings.values()}
    result = _search(ctx, listing_type="rent", property_type="apartment", budget_max=15000, more=True)
    prices = _prices(result)
    assert prices and all(p <= 16500 for p in prices)
    later = {card["id"] for card in ctx.userdata.shown_listings.values()} - first
    assert len(later) == len(prices)


def test_amenity_is_kept_when_bedrooms_empty_the_search():
    # No 2-bed rents under 15,000, but every flat has a lift: the lift isn't the cause.
    result = _search(listing_type="rent", bedrooms=2, amenities=["lift"], budget_max=15000)
    assert "Nothing matched with 'lift'" not in result
    assert "16,500 taka" in result


def test_house_means_any_flat():
    # There are no separate houses: "house" / বাড়ি searches every home.
    ctx = _ctx()
    result = _search(ctx, listing_type="rent", property_type="house", budget_max=20000)
    assert "No matching listings found" not in result
    assert ctx.userdata.shown_listings
    assert all(c["property_type"] == "apartment" for c in ctx.userdata.shown_listings.values())


def test_villa_means_duplex():
    ctx = _ctx()
    _search(ctx, property_type="villa")
    assert ctx.userdata.shown_listings
    assert all(c["property_type"] == "duplex" for c in ctx.userdata.shown_listings.values())


def test_lakh_budget_without_type_searches_sale():
    ctx = _ctx()
    _search(ctx, budget_max=1500000)
    assert ctx.userdata.last_search["listing_type"] == "sale"
    assert all(c["listing_type"] == "sale" for c in ctx.userdata.shown_listings.values())


def test_thousands_budget_without_type_searches_rent():
    ctx = _ctx()
    _search(ctx, budget_max=15000)
    assert ctx.userdata.last_search["listing_type"] == "rent"


def test_sale_at_a_rent_budget_mentions_the_rentals():
    result = _search(listing_type="sale", budget_max=15000)
    assert "homes for rent fit this budget" in result


def test_kept_area_mentions_homes_elsewhere():
    result = _search(location="Gulshan", listing_type="rent", budget_max=15000)
    assert "Elsewhere," in result


def test_kept_bedrooms_mentions_fewer_bedrooms():
    result = _search(listing_type="rent", bedrooms=3, budget_max=15000)
    assert "With fewer bedrooms," in result


def test_either_area_shows_the_one_that_fits():
    ctx = _ctx()
    result = _search(
        ctx, locations=["Dhanmondi", "Mirpur"], location_mode="any", listing_type="rent",
        budget_max=15000,
    )
    assert "No matching listings found" not in result
    assert "Nothing in Dhanmondi matched" in result
    lines = [line for line in result.splitlines() if line.startswith("#")]
    assert lines and all("area: Mirpur" in line for line in lines)


def test_old_comma_location_is_either_area():
    result = _search(location="Dhanmondi, Mirpur", listing_type="rent", budget_max=15000)
    assert "No matching listings found" not in result
    assert "area: Mirpur" in result


def test_both_areas_split_the_slots_evenly():
    result = _search(
        locations=["Mirpur", "Uttara"], location_mode="all", listing_type="rent",
        budget_max=20000,
    )
    lines = [line for line in result.splitlines() if line.startswith("#")]
    in_mirpur = sum("area: Mirpur" in line for line in lines)
    in_uttara = sum("area: Uttara" in line for line in lines)
    assert len(lines) == 5 and {in_mirpur, in_uttara} <= {1, 2, 3} and abs(in_mirpur - in_uttara) <= 2


def test_three_areas_share_the_slots():
    result = _search(
        locations=["Mirpur", "Uttara", "Mohammadpur"], location_mode="all", listing_type="rent",
        budget_max=20000,
    )
    lines = [line for line in result.splitlines() if line.startswith("#")]
    for area in ("Mirpur", "Uttara", "Mohammadpur"):
        assert any(f"area: {area}" in line for line in lines), area


def test_area_with_its_city_still_narrows():
    ctx = _ctx()
    _search(ctx, location="Uttara, Dhaka", listing_type="rent")
    assert ctx.userdata.last_search["location"] == "Uttara, Dhaka"
    assert all("Uttara" in (c["neighborhood"] or "") for c in ctx.userdata.shown_listings.values())
