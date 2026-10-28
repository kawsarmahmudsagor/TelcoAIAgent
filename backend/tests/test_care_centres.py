"""Nearest care centre: the place resolver, the find_care_centre tool and the
snapshot line. The data is static; the tool's default district reads the BSS
(real Postgres via bss_world)."""

import asyncio
from pathlib import Path

import pytest

from app.agent.tools import care_centres as tool
from app.agent.userdata import Channel, SessionUserdata
from app.bss import care_centres
from app.bss.care_centres import CENTRES, DHAKA_AREAS, DISTRICTS, resolve

_KB = Path(care_centres.__file__).resolve().parents[1] / "data" / "kb" / "stores-and-care-centres.md"


def _ud(sub=None) -> SessionUserdata:
    return SessionUserdata(
        channel=Channel.inbound_chat, room=None, subscriber_id=sub.id if sub else None
    )


def test_every_district_of_bangladesh_is_mapped():
    assert len(DISTRICTS) == 64
    for name, (_, centre, _) in DISTRICTS.items():
        assert centre is None and name == "Dhaka" or centre in CENTRES, name
    assert all(centre in CENTRES for _, centre in DHAKA_AREAS.values())


@pytest.mark.parametrize(
    "place, centre",
    [
        ("Gazipur", "Uttara care centre"),
        ("গাজীপুর", "Uttara care centre"),
        ("Gazipur district", "Uttara care centre"),
        ("Chittagong", "GEC Circle care centre"),
        ("cox's bazar", "GEC Circle care centre"),
        ("Coxs Bazar", "GEC Circle care centre"),
        ("Comilla", "Motijheel care centre"),
        ("Gopalganj", "KDA Avenue care centre"),
        ("Kishoreganj", "Ganginarpar care centre"),
        ("Mirpur 10", "Mirpur care centre"),
        ("মিরপুর", "Mirpur care centre"),
        ("Tongi", "Uttara care centre"),
        ("Savar", "Mirpur care centre"),
        ("Gulshan", "telco Experience Centre"),
        ("Narayangonj", "Motijheel care centre"),
        ("Mymensing", "Ganginarpar care centre"),  # misspelt
    ],
)
def test_resolve_finds_the_nearest_centre(place, centre):
    match = resolve(place)
    assert match is not None and match.centre is not None
    assert match.centre.name == centre


def test_meherpur_is_not_mistaken_for_mirpur():
    assert resolve("Meherpur").place == "Meherpur"
    assert resolve("Mirpur").place == "Mirpur"


def test_dhaka_alone_has_no_single_centre():
    match = resolve("ঢাকা")
    assert match.place == "Dhaka" and match.centre is None
    text = care_centres.nearest_text(match)
    assert "which area of Dhaka" in text
    assert all(CENTRES[k].name in text for k in ("gulshan", "mirpur", "motijheel"))


@pytest.mark.parametrize("place", ["", "  ", "Atlantis", "Kolkata"])
def test_unknown_places_do_not_resolve(place):
    assert resolve(place) is None


def test_nearest_text_says_when_the_district_has_no_centre():
    text = care_centres.nearest_text(resolve("Gazipur"))
    assert text.startswith("Nearest care centre to Gazipur: Uttara care centre")
    assert "উত্তরা কেয়ার সেন্টার" in text
    assert "open every day, 9 am to 7 pm" in text
    assert "no care centre in Gazipur itself" in text
    assert "itself" not in care_centres.nearest_text(resolve("Sylhet"))


def test_experience_centre_keeps_its_own_hours():
    assert "9 am to 9 pm" in care_centres.nearest_text(resolve("Banani"))


def test_snapshot_line():
    assert care_centres.snapshot_line("Rajshahi").startswith(
        "Nearest care centre to their district: Shaheb Bazar care centre"
    )
    dhaka = care_centres.snapshot_line("Dhaka")
    assert "ask which area" in dhaka and "find_care_centre" in dhaka
    assert care_centres.snapshot_line("PYTEST-Nowhere") is None


def test_kb_passage_matches_the_centres():
    kb = _KB.read_text(encoding="utf-8")
    for centre in CENTRES.values():
        assert centre.name in kb, centre.name
        assert centre.bn.split(",")[0] in kb, centre.bn
    assert "every day, 9 am to 7 pm" in kb and "9 am to 9 pm" in kb
    assert "সকাল ৯টা থেকে সন্ধ্যা ৭টা" in kb


def test_tool_asks_a_guest_for_a_place():
    assert asyncio.run(tool.run_find_care_centre(_ud())) == tool.ASK_PLACE


def test_tool_names_the_place_it_could_not_match():
    out = asyncio.run(tool.run_find_care_centre(_ud(), "Atlantis"))
    assert '"Atlantis"' in out and "which district" in out


def test_tool_for_a_named_place_needs_no_login():
    out = asyncio.run(tool.run_find_care_centre(_ud(), "Barisal"))
    assert "Sadar Road care centre" in out


def test_tool_defaults_to_the_subscribers_district(bss_world):
    sub = bss_world.subscriber(district="Gazipur")
    out = asyncio.run(tool.run_find_care_centre(_ud(sub)))
    assert "Nearest care centre to Gazipur: Uttara care centre" in out


def test_tool_with_an_unmatched_district_on_file_asks(bss_world):
    sub = bss_world.subscriber(district="PYTEST-Nowhere")
    out = asyncio.run(tool.run_find_care_centre(_ud(sub)))
    assert '"PYTEST-Nowhere"' in out and "which district" in out
