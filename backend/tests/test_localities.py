import pytest

from app.data import localities
from app.data.seed_properties import ALL_PROPERTIES


@pytest.mark.parametrize(
    ("location", "expected"),
    [
        ("Mirpur 12", "Mirpur 12"),
        ("mirpur-12", "Mirpur 12"),
        ("Section 12, Mirpur", "Mirpur 12"),
        ("near Mirpur 12", "Mirpur 12"),
        ("Mirpur 12 er kache", "Mirpur 12"),
        ("Mirpur 12, Dhaka", "Mirpur 12"),
        ("Mirpur ১২", "Mirpur 12"),
        ("Uttara 7", "Uttara Sector 7"),
        ("Sector 7, Uttara", "Uttara Sector 7"),
        ("uttara sec-7", "Uttara Sector 7"),
        ("Uttara 15", "Uttara Sector 15"),
        ("Gulshan 2", "Gulshan 2"),
        ("Dhanmondi 27", "Dhanmondi 27"),
        ("Road 27, Dhanmondi", "Dhanmondi 27"),
        ("Lalmatia", "Lalmatia"),
        ("Lalmatia, Mohammadpur", "Lalmatia"),
        ("Mirpur DOHS", "Mirpur DOHS"),
    ],
)
def test_resolves_sub_areas(location, expected):
    assert localities.resolve_subarea(location) == expected


@pytest.mark.parametrize(
    # Whole areas, unknown places, and a "Sector 7" that could be Purbachal.
    "location",
    ["Mirpur", "Uttara", "Gulshan", "Mohammadpur", "Banani", "Sector 7", "Dhanmondi 8", None, ""],
)
def test_whole_areas_and_ambiguous_places_stay_broad(location):
    assert localities.resolve_subarea(location) is None


def test_mirpur_12_neighbours_closest_first():
    assert localities.nearby("Mirpur 12") == ["Mirpur 11", "Pallabi", "Mirpur DOHS", "Mirpur 10"]


def test_uncurated_sector_gets_numeric_neighbours():
    # No Mirpur 3: x-1 first, then the next sections that exist either side.
    assert localities.resolve_subarea("Mirpur 3") == "Mirpur 3"
    assert localities.nearby("Mirpur 3") == ["Mirpur 2", "Mirpur 1", "Mirpur 6", "Mirpur 7"]
    assert localities.nearby("Uttara Sector 8")[:2] == ["Uttara Sector 7", "Uttara Sector 9"]


def test_every_neighbour_is_a_known_place():
    parents = {area.parent for area in localities.SUBAREAS.values()} | {"Banani", "Baridhara"}
    for area in localities.SUBAREAS.values():
        for near in area.near:
            assert near in localities.SUBAREAS or near in parents, (area.name, near)


def test_seed_has_listings_in_every_sub_area_under_the_parent_area():
    for area in localities.SUBAREAS.values():
        rows = [p for p in ALL_PROPERTIES if p["title"].endswith(f"in {area.name}")]
        assert len(rows) >= 4, area.name
        for row in rows:
            assert row["neighborhood"] == area.parent
            assert area.parent in row["address_line"]
