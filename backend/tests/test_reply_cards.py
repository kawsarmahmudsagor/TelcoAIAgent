"""Package cards for the packages the reply talks about (app.agent.tools.packages
.publish_reply_cards), so a follow-up answered from the conversation, a barge-in
the gate answers itself or a "what else is there?" gets its cards too (run_52,
run_58)."""

import asyncio
import json
from decimal import Decimal
from types import SimpleNamespace

from livekit.agents import llm

from app.agent import cards
from app.agent.gated_agent import GatedAgent, _start_turn
from app.agent.tools import packages as package_tools
from app.agent.topics import PACKAGES
from app.agent.userdata import SessionUserdata
from app.bss.types import PackageView
from app.models.telco import PackageKind


def _pack(code, gb, days, price, minutes=0, name=None) -> PackageView:
    return PackageView(
        code=code, name=name or f"{gb} GB", kind=PackageKind.data if not minutes else PackageKind.bundle,
        data_mb=int(gb * 1024), minutes=minutes, sms=0, validity_days=days,
        price=Decimal(price), tag=None,
    )  # fmt: skip


_CATALOGUE = [
    _pack("D1", 1, 1, 29),
    _pack("D2", 2, 3, 49),
    _pack("D3", 3, 3, 69),
    _pack("D5", 5, 7, 109),
    _pack("D8", 8, 7, 149),
    _pack("B2", 2, 3, 79, minutes=50),
    _pack("B10", 10, 15, 299, minutes=150),
]


class _Participant:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    async def send_text(self, payload, topic, destination_identities):
        self.sent.append((topic, payload))


def _userdata(defer: bool = True) -> SessionUserdata:
    room = SimpleNamespace(local_participant=_Participant())
    userdata = SessionUserdata(channel="web", room=room, linked_identity=lambda: "caller")
    userdata.defer_cards = defer
    userdata.catalogue = list(_CATALOGUE)
    return userdata


def _codes(userdata) -> list[list[str]]:
    return [
        [p["code"] for p in json.loads(payload)["packages"]]
        for topic, payload in userdata.room.local_participant.sent
        if topic == PACKAGES
    ]


def _codes_of(found) -> list[str]:
    return [p.code for p in found]


async def _publish(userdata, text):
    """A finished reply's card decision, then its speech starting."""
    await package_tools.publish_reply_cards(userdata, text)
    await cards.cards_ready(userdata)
    await cards.reply_speaking(userdata)


# --- matching --------------------------------------------------------------------------


def test_each_sentence_finds_its_package():
    text = "২৯ টাকায় ১ জিবি, মেয়াদ ১ দিন। ৪৯ টাকায় ২ জিবি, মেয়াদ ৩ দিন।"
    assert _codes_of(package_tools.reply_packages(_CATALOGUE, text)) == ["D1", "D2"]


def test_a_bundle_by_its_data_minutes_and_price():
    text = "এই প্যাকেজে ২ জিবি ডাটা আর ৫০ মিনিট পাবেন, ৭৯ টাকায়। মেয়াদ ৩ দিন।"
    assert _codes_of(package_tools.reply_packages(_CATALOGUE, text)) == ["B2"]


def test_english_reply():
    assert _codes_of(package_tools.reply_packages(_CATALOGUE, "1 GB for 29 taka, valid 1 day.")) == ["D1"]


def test_a_price_alone_is_no_package():
    # A purchase confirm or a charge names the price only.
    for text in (
        "প্যাকেজটির ১০৯ টাকা আপনার ব্যালেন্স থেকে কাটা হবে।",
        "৭৯ টাকার প্যাকেজটা চালু করে দেবো?",
        "আপনার ব্যালেন্স ৭৩০.২৫ টাকা।",
        "প্যাকেজে ১১.৭ জিবি ডাটা আর ১৫০ মিনিট আছে।",
    ):
        assert package_tools.reply_packages(_CATALOGUE, text) == [], text


# --- publishing ------------------------------------------------------------------------


def test_a_follow_up_answered_from_the_conversation_gets_its_card():
    # run_58 turn 2: no search ran this turn.
    userdata = _userdata()
    _start_turn(userdata, "আমাকে শুধু এক GB-র প্যাকেজটা সম্পর্কে বলুন")
    asyncio.run(_publish(userdata, "১ জিবির ডাটা প্যাকেজটি ২৯ টাকায়, মেয়াদ ১ দিন।"))
    assert _codes(userdata) == [["D1"]]


def test_packages_on_this_turns_card_are_not_sent_again():
    # run_58 turn 1: the search card already shows them.
    userdata = _userdata(defer=False)
    _start_turn(userdata, "কি কি data package আছে?")

    async def go():
        await package_tools._publish_cards(userdata, "Packages", _CATALOGUE[:5])
        await package_tools.publish_reply_cards(
            userdata, "২৯ টাকায় ১ জিবি, মেয়াদ ১ দিন। ৪৯ টাকায় ২ জিবি, মেয়াদ ৩ দিন।"
        )

    asyncio.run(go())
    assert _codes(userdata) == [["D1", "D2", "D3", "D5", "D8"]]


def test_more_packages_get_their_own_card():
    # run_52: "আর কি কি options আছে?" -- the search card repeats the first set
    # (dropped as shown), the reply goes on to the next ones.
    userdata = _userdata(defer=False)

    async def go():
        _start_turn(userdata, "কি কি প্যাকেজ আছে?")
        await package_tools._publish_cards(userdata, "Packages", _CATALOGUE[:2])
        _start_turn(userdata, "আর কি কি options আছে?")
        await package_tools._publish_cards(userdata, "Packages", _CATALOGUE[:2])
        await package_tools.publish_reply_cards(
            userdata, "৬৯ টাকায় ৩ জিবি, মেয়াদ ৩ দিন। ১০৯ টাকায় ৫ জিবি, মেয়াদ ৭ দিন।"
        )

    asyncio.run(go())
    assert _codes(userdata) == [["D1", "D2"], ["D3", "D5"]]


def test_the_same_set_twice_in_a_row_is_sent_once():
    userdata = _userdata()

    async def go():
        for turn in ("এক জিবিরটা?", "আবার বলুন"):
            _start_turn(userdata, turn)
            await _publish(userdata, "২৯ টাকায় ১ জিবি, মেয়াদ ১ দিন।")

    asyncio.run(go())
    assert _codes(userdata) == [["D1"]]


def test_no_amounts_never_loads_the_catalogue():
    userdata = _userdata()
    userdata.catalogue = None  # a DB load would fail here: no database in this test
    asyncio.run(_publish(userdata, "জি, আর কিছু জানতে চাচ্ছেন?"))
    assert _codes(userdata) == []


# --- the main model's stream -----------------------------------------------------------


async def _stream(*items):
    for item in items:
        yield item


def _chunk(content):
    return llm.ChatChunk(id="x", delta=llm.ChoiceDelta(role="assistant", content=content))


def test_the_reply_stream_sends_the_cards_it_talks_about():
    userdata = _userdata()
    _start_turn(userdata, "শুধু এক GB-র প্যাকেজটা")
    agent = SimpleNamespace(session=SimpleNamespace(userdata=userdata))

    async def go():
        async for _ in GatedAgent._cards_with_speech(
            agent, _stream(_chunk("১ জিবির ডাটা প্যাকেজটি "), _chunk("২৯ টাকায়, মেয়াদ ১ দিন।"))
        ):
            pass

    asyncio.run(go())
    assert _codes(userdata) == []  # held until the reply speaks
    asyncio.run(cards.reply_speaking(userdata))
    assert _codes(userdata) == [["D1"]]


def _run_reply(userdata, *parts):
    agent = SimpleNamespace(session=SimpleNamespace(userdata=userdata))

    async def go():
        async for _ in GatedAgent._cards_with_speech(agent, _stream(*[_chunk(p) for p in parts])):
            pass
        await cards.reply_speaking(userdata)

    asyncio.run(go())


def test_the_reply_card_replaces_the_search_card():
    # The search found the cheapest six; the reply named three others: one
    # card, the three the customer hears about.
    userdata = _userdata()
    _start_turn(userdata, "আমার জন্য কি কি data package আছে?")
    asyncio.run(package_tools._publish_cards(userdata, "Packages", _CATALOGUE[:5]))
    _run_reply(
        userdata,
        "আপাতত ১০৯ টাকায় ৫ জিবি, মেয়াদ ৭ দিন। ",
        "১৪৯ টাকায় ৮ জিবি, মেয়াদ ৭ দিন। ২৯৯ টাকায় ১০ জিবি আর ১৫০ মিনিট, মেয়াদ ১৫ দিন।",
    )
    assert _codes(userdata) == [["D5", "D8", "B10"]]


def test_a_reply_naming_no_package_shows_the_search_card():
    userdata = _userdata()
    _start_turn(userdata, "কি কি data package আছে?")
    asyncio.run(package_tools._publish_cards(userdata, "Packages", _CATALOGUE[:3]))
    _run_reply(userdata, "কয়েকটা ডাটা প্যাকেজ আছে, ", "কোন মেয়াদের চাচ্ছেন?")
    assert _codes(userdata) == [["D1", "D2", "D3"]]


def test_a_dropped_search_card_does_not_count_as_shown():
    userdata = _userdata()
    _start_turn(userdata, "এক জিবিরটা?")
    _run_reply(userdata, "২৯ টাকায় ১ জিবি, মেয়াদ ১ দিন।")
    _start_turn(userdata, "আর কি আছে?")
    asyncio.run(package_tools._publish_cards(userdata, "Packages", _CATALOGUE[1:3]))
    _run_reply(userdata, "৪৯ টাকায় ২ জিবি, মেয়াদ ৩ দিন।")
    _start_turn(userdata, "এক জিবিরটা আবার বলেন")
    _run_reply(userdata, "২৯ টাকায় ১ জিবি, মেয়াদ ১ দিন।")
    assert _codes(userdata) == [["D1"], ["D2"], ["D1"]]


def test_two_searches_and_a_reply_naming_one_of_each_give_one_card():
    # run_60: data and voice searched in one turn; the reply named the cheapest
    # of each. Two rows came: the voice search card, then the reply's.
    voice = [
        PackageView(
            code=f"V{m}", name=f"{m} Minutes", kind=PackageKind.voice, data_mb=0, minutes=m,
            sms=0, validity_days=days, price=Decimal(price), tag=None,
        )
        for m, days, price in ((50, 3, 39), (100, 7, 79), (300, 30, 199))
    ]  # fmt: skip
    userdata = _userdata()
    userdata.catalogue = [*_CATALOGUE, *voice]
    _start_turn(userdata, "সবথেকে কম দামের ডেটা প্যাকেজ এবং মিনিট প্যাকেজ কোনটা?")

    async def searches():
        await package_tools._publish_cards(userdata, "Packages", _CATALOGUE[:5])
        await package_tools._publish_cards(userdata, "Packages", voice)

    asyncio.run(searches())
    _run_reply(
        userdata,
        "সবচেয়ে কম দামের ডাটা প্যাকেজ ২৯ টাকায় ১ জিবি, মেয়াদ ১ দিন। ",
        "সবচেয়ে কম দামের মিনিট প্যাকেজ ৩৯ টাকায় ৫০ মিনিট, মেয়াদ ৩ দিন।",
    )
    assert _codes(userdata) == [["D1", "V50"]]

