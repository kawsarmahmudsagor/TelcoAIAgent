"""The prompt's account snapshot follows the DB during a session, off the
reply path: load_snapshot re-reads it, and SnapshotRefresher swaps in only a
changed snapshot, leaving the rest of the instructions byte-identical."""

import asyncio
import uuid
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import select

from app.agent import snapshot_refresh
from app.agent.snapshot import load_session_context, load_snapshot
from app.agent.userdata import Channel, SessionUserdata
from app.models.telco import Balance


def test_load_snapshot_reads_the_current_balance(bss_world):
    sub = bss_world.subscriber(full_name="Samiha Khan", main_balance=Decimal("486.50"))
    first = load_session_context(sub.id, None).snapshot
    assert load_snapshot(sub.id) == first

    bal = bss_world.db.scalar(select(Balance).where(Balance.subscriber_id == sub.id))
    bal.main_balance = Decimal("337.50")
    bss_world.db.commit()

    fresh = load_snapshot(sub.id)
    assert fresh != first and "337.50" in fresh and "486.50" not in fresh


def test_load_snapshot_unknown_subscriber_is_none(db):
    assert load_snapshot(uuid.uuid4()) is None


class FakeSession:
    def __init__(self):
        self.handlers: dict[str, list] = {}
        self.agent_state = "listening"

    def on(self, event, handler):
        self.handlers.setdefault(event, []).append(handler)

    def emit(self, event, **fields):
        for handler in self.handlers.get(event, []):
            handler(SimpleNamespace(**fields))


class FakeAgent:
    def __init__(self, instructions: str):
        self.instructions = instructions
        self.updates: list[str] = []

    async def update_instructions(self, instructions: str) -> None:
        self.updates.append(instructions)
        self.instructions = instructions


OLD = "ACCOUNT SNAPSHOT\nMain balance: 486.50 taka."
NEW = "ACCOUNT SNAPSHOT\nMain balance: 337.50 taka."
PROMPT = f"IDENTITY date 10:42\n{OLD}\n\nTASK"


def _refresher(monkeypatch, reads: list[str | None], *, interval_s: float = 0):
    calls = []

    def fake_load(subscriber_id):
        calls.append(subscriber_id)
        return reads.pop(0) if reads else NEW

    monkeypatch.setattr(snapshot_refresh, "load_snapshot", fake_load)
    session = FakeSession()
    agent = FakeAgent(PROMPT)
    userdata = SessionUserdata(channel=Channel.inbound_chat, room=None)
    userdata.subscriber_id = uuid.uuid4()
    userdata.snapshot_text = OLD
    refresher = snapshot_refresh.SnapshotRefresher(
        session=session, agent=agent, userdata=userdata, interval_s=interval_s
    )
    refresher.attach()
    refresher.start()
    return refresher, session, agent, userdata, calls


async def _settle():
    for _ in range(20):
        await asyncio.sleep(0.01)


def test_a_changed_snapshot_replaces_only_its_own_text(monkeypatch):
    async def go():
        _, session, agent, userdata, _ = _refresher(monkeypatch, [NEW])
        session.emit("agent_state_changed", new_state="listening")
        await _settle()
        assert agent.updates == [f"IDENTITY date 10:42\n{NEW}\n\nTASK"]
        assert userdata.snapshot_text == NEW

    asyncio.run(go())


def test_an_unchanged_snapshot_leaves_the_prompt_alone(monkeypatch):
    """No update means the provider's prompt cache keeps hitting."""

    async def go():
        _, session, agent, _, calls = _refresher(monkeypatch, [OLD])
        session.emit("user_state_changed", new_state="speaking")
        await _settle()
        assert len(calls) == 1 and agent.updates == []

    asyncio.run(go())


def test_only_turn_boundaries_trigger_a_read(monkeypatch):
    async def go():
        _, session, _, _, calls = _refresher(monkeypatch, [OLD, OLD])
        session.emit("agent_state_changed", new_state="thinking")
        session.emit("agent_state_changed", new_state="speaking")
        session.emit("user_state_changed", new_state="listening")
        await _settle()
        assert calls == []

    asyncio.run(go())


def test_triggers_during_a_read_are_coalesced(monkeypatch):
    async def go():
        _, session, _, _, calls = _refresher(monkeypatch, [OLD, OLD, OLD])
        session.emit("agent_state_changed", new_state="listening")
        session.emit("user_state_changed", new_state="speaking")
        session.emit("agent_state_changed", new_state="listening")
        await _settle()
        assert len(calls) == 1

    asyncio.run(go())


def test_the_timer_refreshes_while_listening_and_stops_on_close(monkeypatch):
    async def go():
        _, session, agent, _, calls = _refresher(monkeypatch, [NEW], interval_s=0.02)
        await asyncio.sleep(0.1)
        assert calls and agent.updates
        session.emit("close")
        seen = len(calls)
        await asyncio.sleep(0.1)
        assert len(calls) == seen

    asyncio.run(go())


def test_a_failed_read_keeps_the_old_snapshot(monkeypatch):
    async def go():
        _, session, agent, userdata, _ = _refresher(monkeypatch, [])

        def boom(subscriber_id):
            raise RuntimeError("db down")

        monkeypatch.setattr(snapshot_refresh, "load_snapshot", boom)
        session.emit("agent_state_changed", new_state="listening")
        await _settle()
        assert agent.updates == [] and userdata.snapshot_text == OLD

    asyncio.run(go())
