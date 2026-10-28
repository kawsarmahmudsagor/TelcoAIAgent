"""Cards with quick replies on: held until the main model's first words, so they
don't appear while a filler line plays (app.agent.cards)."""

import asyncio
from types import SimpleNamespace

from livekit.agents import llm

from app.agent.gated_agent import GatedAgent
from app.agent.cards import flush_pending_card, send_card
from app.agent.userdata import SessionUserdata

_TOPIC = "telco.test"
_CARDS = '[{"id": "1"}]'


class _Participant:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    async def send_text(self, payload, topic, destination_identities):
        assert destination_identities == ["caller"]
        self.sent.append((topic, payload))


def _userdata(*, defer: bool) -> SessionUserdata:
    participant = _Participant()
    room = SimpleNamespace(local_participant=participant)
    userdata = SessionUserdata(channel="web", room=room, linked_identity=lambda: "caller")
    userdata.defer_cards = defer
    return userdata


def _sent(userdata) -> list[tuple[str, str]]:
    return userdata.room.local_participant.sent


def _chunk(content=None, tool_call=False):
    calls = [llm.FunctionToolCall(name="x", arguments="{}", call_id="c")] if tool_call else []
    return llm.ChatChunk(id="x", delta=llm.ChoiceDelta(role="assistant", content=content, tool_calls=calls))


async def _stream(*items):
    for item in items:
        yield item


async def _run(userdata, *items):
    agent = SimpleNamespace(session=SimpleNamespace(userdata=userdata))
    seen: list[int] = []
    async for _ in GatedAgent._cards_with_speech(agent, _stream(*items)):
        seen.append(len(_sent(userdata)))  # cards sent by the time this chunk was passed on
    return seen


def test_send_card_immediate_when_not_deferred():
    async def go():
        userdata = _userdata(defer=False)
        await send_card(userdata, _TOPIC, _CARDS)
        assert _sent(userdata) == [(_TOPIC, _CARDS)]
        assert userdata.pending_card is None

    asyncio.run(go())


def test_send_card_deferred_then_flushed():
    async def go():
        userdata = _userdata(defer=True)
        await send_card(userdata, _TOPIC, _CARDS)
        assert _sent(userdata) == [] and userdata.pending_card == (_TOPIC, _CARDS)
        assert await flush_pending_card(userdata) is True
        assert _sent(userdata) == [(_TOPIC, _CARDS)]
        assert userdata.pending_card is None

    asyncio.run(go())


def test_flush_without_pending_card_returns_false():
    async def go():
        assert await flush_pending_card(_userdata(defer=True)) is False

    asyncio.run(go())


def test_the_latest_card_replaces_a_held_one():
    async def go():
        userdata = _userdata(defer=True)
        await send_card(userdata, _TOPIC, '["old"]')
        await send_card(userdata, _TOPIC, '["new"]')
        await flush_pending_card(userdata)
        assert _sent(userdata) == [(_TOPIC, '["new"]')]

    asyncio.run(go())


def test_cards_come_with_the_first_words_of_the_main_reply():
    async def go():
        userdata = _userdata(defer=True)
        await send_card(userdata, _TOPIC, _CARDS)
        # a tool-call step has no words: nothing yet; the words bring the cards
        seen = await _run(userdata, _chunk(tool_call=True), _chunk(""), _chunk("এই"), _chunk(" যে"))
        assert seen == [0, 0, 1, 1]
        assert len(_sent(userdata)) == 1

    asyncio.run(go())


def test_a_last_step_without_words_still_shows_the_cards():
    async def go():
        userdata = _userdata(defer=True)
        await send_card(userdata, _TOPIC, _CARDS)
        await _run(userdata, _chunk(""))
        assert len(_sent(userdata)) == 1

    asyncio.run(go())


def test_a_tool_call_step_keeps_the_cards_for_the_next_step():
    async def go():
        userdata = _userdata(defer=True)
        await send_card(userdata, _TOPIC, _CARDS)
        await _run(userdata, _chunk(tool_call=True))
        assert _sent(userdata) == [] and userdata.pending_card == (_TOPIC, _CARDS)

    asyncio.run(go())


def _pkg(code, minutes=0, data_mb=0):
    from decimal import Decimal

    from app.bss.types import PackageView
    from app.models.telco import PackageKind

    return PackageView(
        code=code, name=code, kind=PackageKind.voice, data_mb=data_mb, minutes=minutes, sms=0,
        validity_days=7, price=Decimal("79"), tag=None,
    )


def test_package_cards_show_only_the_size_asked_about_and_never_repeat():
    import json

    from app.agent.tools import packages

    found = [_pkg("V50", minutes=50), _pkg("V100", minutes=100), _pkg("V300", minutes=300)]

    async def go():
        userdata = _userdata(defer=False)
        userdata.turn_text = "মিনিটের প্যাকেজ দেখান"
        await packages._publish_cards(userdata, "Packages", found)
        await packages._publish_cards(userdata, "Packages", found)  # same set: not again
        userdata.turn_text = "একশো মিনিটের প্যাকেজটি সম্পর্কে বলুন"
        await packages._publish_cards(userdata, "Packages", found)
        return [[p["code"] for p in json.loads(payload)["packages"]] for _, payload in _sent(userdata)]

    assert asyncio.run(go()) == [["V50", "V100", "V300"], ["V100"]]
