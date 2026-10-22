"""The shortlist cards with quick replies on: held until the main model's first
words, so they don't appear while a filler line plays."""

import asyncio
from types import SimpleNamespace

from livekit.agents import llm

from app.agent.gated_agent import GatedAgent
from app.agent.tools.search_apartments import flush_shortlist, send_shortlist
from app.agent.userdata import SessionUserdata

_CARDS = '[{"id": "1"}]'


class _Participant:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    async def send_text(self, payload, topic):
        self.sent.append((topic, payload))


def _userdata(*, defer: bool) -> SessionUserdata:
    participant = _Participant()
    room = SimpleNamespace(local_participant=participant)
    userdata = SessionUserdata(channel="web", room=room)
    userdata.defer_cards = defer
    userdata.focused_listing = 3
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


def test_cards_go_at_once_without_quick_replies():
    async def go():
        userdata = _userdata(defer=False)
        await send_shortlist(userdata, _CARDS, True)
        assert _sent(userdata) == [("apartment-shortlist", _CARDS)]
        assert userdata.focused_listing is None

    asyncio.run(go())


def test_cards_wait_when_deferred():
    async def go():
        userdata = _userdata(defer=True)
        await send_shortlist(userdata, _CARDS, True)
        assert _sent(userdata) == [] and userdata.focused_listing == 3
        assert await flush_shortlist(userdata) is True
        assert _sent(userdata) == [("apartment-shortlist", _CARDS)]
        assert userdata.focused_listing is None
        assert await flush_shortlist(userdata) is False  # nothing left

    asyncio.run(go())


def test_the_latest_search_replaces_a_held_one():
    async def go():
        userdata = _userdata(defer=True)
        await send_shortlist(userdata, '["old"]', True)
        await send_shortlist(userdata, '["new"]', True)
        await flush_shortlist(userdata)
        assert _sent(userdata) == [("apartment-shortlist", '["new"]')]

    asyncio.run(go())


def test_cards_come_with_the_first_words_of_the_main_reply():
    async def go():
        userdata = _userdata(defer=True)
        await send_shortlist(userdata, _CARDS, True)
        # a tool-call step has no words: nothing yet; the words bring the cards
        seen = await _run(userdata, _chunk(tool_call=True), _chunk(""), _chunk("এই"), _chunk(" যে"))
        assert seen == [0, 0, 1, 1]
        assert len(_sent(userdata)) == 1

    asyncio.run(go())


def test_a_last_step_without_words_still_shows_the_cards():
    async def go():
        userdata = _userdata(defer=True)
        await send_shortlist(userdata, _CARDS, True)
        await _run(userdata, _chunk(""))
        assert len(_sent(userdata)) == 1

    asyncio.run(go())


def test_a_tool_call_step_keeps_the_cards_for_the_next_step():
    async def go():
        userdata = _userdata(defer=True)
        await send_shortlist(userdata, _CARDS, True)
        await _run(userdata, _chunk(tool_call=True))
        assert _sent(userdata) == [] and userdata.pending_cards == _CARDS

    asyncio.run(go())
