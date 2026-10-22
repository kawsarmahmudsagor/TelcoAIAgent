"""The property page's viewing_property_id attribute -> the agent's prompt. The
room, participant and agent are fakes; listings come from a stub loader."""

import asyncio
import threading
import uuid
from types import SimpleNamespace

from app.agent.userdata import Channel, SessionUserdata
from app.agent.viewing_context import VIEWING_ATTRIBUTE, ViewingContext

BASE_PROMPT = "You are a real-estate assistant."
CALLER = "web-user"


def _card(property_id: uuid.UUID, title: str) -> dict:
    return {
        "id": str(property_id),
        "title": title,
        "address_line": "Road 1",
        "city": "Dhaka",
        "neighborhood": "Gulshan",
        "price": 45000.0,
        "listing_type": "rent",
        "property_type": "apartment",
        "bedrooms": 3,
        "bathrooms": 2.0,
        "sqft": 1400,
        "amenities": ["lift"],
        "image_url": None,
        "images": None,
    }


class FakeAgent:
    def __init__(self):
        self.instructions = BASE_PROMPT
        self.updates: list[str] = []

    async def update_instructions(self, instructions: str) -> None:
        self.instructions = instructions
        self.updates.append(instructions)


class FakeRoom:
    def __init__(self, participants=()):
        self.remote_participants = {p.identity: p for p in participants}
        self.handlers: dict[str, object] = {}

    def on(self, event, handler):
        self.handlers[event] = handler


def _participant(identity=CALLER, **attributes):
    return SimpleNamespace(identity=identity, attributes=attributes)


def _context(listings: dict[uuid.UUID, dict], room: FakeRoom | None = None):
    agent = FakeAgent()
    userdata = SessionUserdata(channel=Channel.inbound_chat, room=room)
    context = ViewingContext(
        agent=agent,
        userdata=userdata,
        base_prompt=BASE_PROMPT,
        linked_identity=lambda: CALLER,
        load_card=listings.get,
    )
    context.attach(room or FakeRoom())
    return context, agent, userdata


def test_viewed_listing_gets_a_number_and_a_note():
    async def go():
        pid = uuid.uuid4()
        room = FakeRoom()
        context, agent, userdata = _context({pid: _card(pid, "Lakeview Flat")}, room)
        room.handlers["participant_attributes_changed"](
            {VIEWING_ATTRIBUTE: str(pid)}, _participant(**{VIEWING_ATTRIBUTE: str(pid)})
        )
        await context.settle()

        assert userdata.viewing_property_id == pid
        assert userdata.shown_listings[1]["id"] == str(pid)
        assert agent.instructions.startswith(BASE_PROMPT)
        assert "viewing listing #1: Lakeview Flat, Gulshan, 45,000 taka" in agent.instructions

    asyncio.run(go())


def test_already_shown_listing_keeps_its_number():
    async def go():
        shown, viewed = uuid.uuid4(), uuid.uuid4()
        listings = {shown: _card(shown, "First"), viewed: _card(viewed, "Second")}
        context, agent, userdata = _context(listings)
        userdata.shown_listings[1] = listings[shown]
        userdata.shown_listings[2] = listings[viewed]

        await context.apply(str(viewed))
        assert "listing #2: Second" in agent.instructions
        assert len(userdata.shown_listings) == 2

    asyncio.run(go())


def test_empty_value_drops_the_note():
    async def go():
        pid = uuid.uuid4()
        context, agent, userdata = _context({pid: _card(pid, "Lakeview Flat")})
        await context.apply(str(pid))
        assert agent.instructions != BASE_PROMPT

        await context.apply("")
        assert agent.instructions == BASE_PROMPT
        assert userdata.viewing_property_id is None

    asyncio.run(go())


def test_switching_pages_replaces_the_note_instead_of_stacking():
    async def go():
        a, b = uuid.uuid4(), uuid.uuid4()
        context, agent, _ = _context({a: _card(a, "Alpha"), b: _card(b, "Bravo")})
        await context.apply(str(a))
        await context.apply(str(b))
        assert "Alpha" not in agent.instructions
        assert agent.instructions.count("currently viewing") == 1

    asyncio.run(go())


def test_unknown_or_malformed_listing_clears_the_note():
    async def go():
        context, agent, userdata = _context({})
        await context.apply(str(uuid.uuid4()))
        await context.apply("not-a-uuid")
        assert agent.updates == [BASE_PROMPT, BASE_PROMPT]
        assert userdata.shown_listings == {}

    asyncio.run(go())


def test_other_participants_and_attributes_are_ignored():
    async def go():
        pid = uuid.uuid4()
        room = FakeRoom()
        context, agent, _ = _context({pid: _card(pid, "Lakeview Flat")}, room)
        handler = room.handlers["participant_attributes_changed"]
        handler({VIEWING_ATTRIBUTE: str(pid)}, _participant("someone-else"))
        handler({"turn_gate": "1"}, _participant())
        await context.settle()
        assert agent.updates == []

    asyncio.run(go())


def test_value_set_before_the_agent_joined_is_read_on_attach():
    async def go():
        pid = uuid.uuid4()
        room = FakeRoom([_participant(**{VIEWING_ATTRIBUTE: str(pid)})])
        context, agent, userdata = _context({pid: _card(pid, "Lakeview Flat")}, room)
        await context.settle()
        assert userdata.viewing_property_id == pid
        assert "Lakeview Flat" in agent.instructions

    asyncio.run(go())


def test_a_stale_load_never_overwrites_a_newer_page():
    async def go():
        slow, fast = uuid.uuid4(), uuid.uuid4()
        release = threading.Event()
        listings = {slow: _card(slow, "Slow"), fast: _card(fast, "Fast")}

        def load(pid):
            if pid == slow:
                release.wait(timeout=5)
            return listings[pid]

        room = FakeRoom()
        context, agent, _ = _context(listings, room)
        context._load_card = load
        handler = room.handlers["participant_attributes_changed"]
        handler({VIEWING_ATTRIBUTE: str(slow)}, _participant())
        handler({VIEWING_ATTRIBUTE: str(fast)}, _participant())
        while not agent.updates:
            await asyncio.sleep(0.01)
        release.set()
        await context.settle()

        assert len(agent.updates) == 1
        assert "Fast" in agent.instructions

    asyncio.run(go())
