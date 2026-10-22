"""The first message (the greeting) can't be interrupted: until it has played out
the session ignores the customer's voice (turn gate) and typed text, and
afterwards nothing heard during it leaks into the first real turn. The
AgentSession and room are fakes; the judge is a stub."""

import asyncio
import contextlib
from types import SimpleNamespace

from livekit import rtc
from test_gated_session import FakeRoom, FakeSession, _complete, _controller, _heard, _settle

from app.agent import entrypoint, gated_agent
from app.agent.gated_agent import IGNORED_TEXT_TOPIC, USER_TURN_TOPIC
from app.agent.prompt_defaults import (
    SALAM,
    SALAM_INSTRUCTION,
    SPOKEN_GREETINGS_INBOUND,
)
from app.agent.userdata import Channel, SessionUserdata
from app.services import agent_config_service


def _during_greeting(scores=0.9):
    gate, session, room, judged = _controller(scores)
    session.userdata.greeting_done = False
    return gate, session, room, judged


def _agent(gate) -> gated_agent.GatedAgent:
    return gated_agent.GatedAgent(gate=gate, instructions="test")


# ---- gated voice ----


def test_speech_during_the_greeting_never_barges_in():
    async def go():
        gate, session, room, judged = _during_greeting(0.9)
        session.agent_state = "speaking"
        _heard(gate, "Hold on, what was the price again?")
        _heard(gate, "না না,", final=False)  # a stop phrase too
        await _settle(gate)
        assert session.calls == []
        assert room.sent == []
        assert judged == []

    asyncio.run(go())


def test_speech_during_the_greeting_is_not_queued_as_an_answer():
    async def go():
        gate, session, room, judged = _during_greeting(0.8)
        session.agent_state = "thinking"
        _heard(gate, "হ্যাঁ")
        await _settle(gate)
        assert session.calls == []
        assert room.sent == []
        assert judged == []

    asyncio.run(go())


def test_a_turn_completed_during_the_greeting_is_dropped():
    async def go():
        gate, session, room, judged = _during_greeting(0.9)
        assert not await _complete(gate, "Is parking included?")
        assert room.sent == []
        assert judged == []

    asyncio.run(go())


def test_greeting_done_resets_the_gate():
    async def go():
        gate, _, _, _ = _controller(0.8)
        _heard(gate, "আমার বাজেট")
        await asyncio.sleep(0)
        assert gate._buffer and gate._judged
        _agent(gate).on_greeting_done()
        assert gate._buffer == []
        assert gate._judged == {}

    asyncio.run(go())


def test_speech_during_the_greeting_then_a_new_utterance_is_accepted():
    async def go():
        gate, session, room, judged = _during_greeting(0.8)
        session.agent_state = "speaking"
        _heard(gate, "আমার বাজেট")
        await _settle(gate)

        await entrypoint._mark_greeting_done(session, _agent(gate), session.userdata, None)
        assert ("clear_user_turn",) in session.calls

        session.agent_state = "listening"
        _heard(gate, "Is parking included?")
        await asyncio.sleep(0)
        # judged on its own, not joined to what was said during the greeting
        assert judged == [("Is parking included?", "listening")]
        assert await _complete(gate, "Is parking included?")
        assert room.sent == [(USER_TURN_TOPIC, "Is parking included?")]

    asyncio.run(go())


# ---- typed text ----


class TextSession(FakeSession):
    current_agent = None

    @contextlib.asynccontextmanager
    async def _claim_user_turn(self):
        yield


def test_text_before_the_greeting_is_dropped_and_after_it_goes_through():
    async def go():
        session = TextSession()
        session.userdata.greeting_done = False
        await gated_agent._text_input_cb(session, SimpleNamespace(text="hello?"))
        assert session.calls == []

        session.userdata.greeting_done = True
        await gated_agent._text_input_cb(session, SimpleNamespace(text="Is parking included?"))
        assert session.calls == [("interrupt", True), ("generate_reply", "Is parking included?")]

    asyncio.run(go())


def _typed(text: str, message_id: str = "TS_1"):
    # The real TextStreamInfo: its id field is stream_id (the JS SDK calls it id).
    info = rtc.TextStreamInfo(
        stream_id=message_id,
        mime_type="text/plain",
        topic="lk.chat",
        timestamp=0,
        size=None,
        attributes=None,
        attachments=[],
    )
    return SimpleNamespace(text=text, info=info)


def _gated_text_session(scores):
    gate, _, room, judged = _controller(scores)
    session = TextSession()
    gate.session = session
    session.current_agent = _agent(gate)
    return session, room, judged


def test_off_topic_typed_text_is_ignored_and_taken_off_the_transcript():
    async def go():
        cricket = "বাংলাদেশের ক্রিকেট টিম সম্পর্কে বলুন"
        session, room, judged = _gated_text_session({cricket: 0.05})
        session.agent_state = "speaking"
        await gated_agent._text_input_cb(session, _typed(cricket, "TS_cricket"))
        # no interrupt, no reply
        assert session.calls == []
        assert judged == [(cricket, "listening")]
        assert room.sent == [(IGNORED_TEXT_TOPIC, cricket)]
        assert room.payloads[-1]["id"] == "TS_cricket"

    asyncio.run(go())


def test_on_topic_typed_text_is_answered():
    async def go():
        for score in (0.9, None):  # None: the judge failed, so it's answered
            session, room, _ = _gated_text_session(score)
            await gated_agent._text_input_cb(session, _typed("Is parking included?"))
            assert session.calls == [
                ("interrupt", True),
                ("generate_reply", "Is parking included?"),
            ]
            assert room.sent == []

    asyncio.run(go())


def test_sound_tag_typed_text_is_not_answered():
    async def go():
        session, _, judged = _gated_text_session(0.9)
        await gated_agent._text_input_cb(session, _typed("[clears throat]"))
        assert judged == []
        assert not any(call[0] == "generate_reply" for call in session.calls)

    asyncio.run(go())


def test_filler_typed_text_skips_the_judge():
    async def go():
        session, _, judged = _gated_text_session(0.0)
        await gated_agent._text_input_cb(session, _typed("hmm"))
        assert judged == []
        assert ("generate_reply", "hmm") in session.calls

    asyncio.run(go())


# ---- _greet ----


class FakeHandle:
    def __init__(self, *, raises: Exception | None = None, error: Exception | None = None):
        self._raises = raises
        self._error = error

    async def wait_for_playout(self):
        await asyncio.sleep(0)
        if self._raises is not None:
            raise self._raises

    def exception(self):
        return self._error


class GreetSession:
    def __init__(self, handle: FakeHandle, *, closed: bool = False):
        self.handle = handle
        self.closed = closed
        self.replies: list[dict] = []
        self.cleared = 0
        self.agent_state = "listening"

    def generate_reply(self, **kwargs):
        self.replies.append({"kind": "generate_reply", **kwargs})
        return self.handle

    def say(self, text, **kwargs):
        self.replies.append({"kind": "say", "text": text, **kwargs})
        return self.handle

    def clear_user_turn(self):
        if self.closed:
            raise RuntimeError("AgentSession isn't running")
        self.cleared += 1


class AttributeRoom(FakeRoom):
    def __init__(self, userdata_probe=None):
        super().__init__()
        self.attributes: dict[str, str] = {}
        # Each set_attributes call, as sent.
        self.updates: list[dict[str, str]] = []
        # Whether the session was already open to input when the update went out.
        self.open_at_update: list[bool] = []
        self.userdata_probe = userdata_probe

    async def set_attributes(self, attributes):
        if self.userdata_probe is not None:
            self.open_at_update.append(self.userdata_probe().greeting_done)
        self.updates.append(dict(attributes))
        self.attributes.update(attributes)


class GreetAgent:
    def __init__(self):
        self.greeting_done_calls = 0

    def on_greeting_done(self):
        self.greeting_done_calls += 1


async def _greet(
    handle: FakeHandle,
    *,
    room=None,
    closed=False,
    config=None,
):
    session = GreetSession(handle, closed=closed)
    agent = GreetAgent()
    userdata = SessionUserdata(channel=Channel.inbound_chat, room=room)
    config = config or agent_config_service.resolve(None)
    entrypoint._greet(session, agent, userdata, config, room=room)
    for _ in range(10):
        await asyncio.sleep(0)
    return session, agent, userdata


def test_greeting_is_uninterruptible_and_unlocks_the_session():
    async def go():
        room = AttributeRoom()
        session, agent, userdata = await _greet(FakeHandle(), room=room)
        assert [r["allow_interruptions"] for r in session.replies] == [False]
        assert userdata.greeting_done
        assert session.cleared == 1
        assert agent.greeting_done_calls == 1
        assert room.attributes == {"greeting_done": "1"}

    asyncio.run(go())


def test_greeting_done_update_precedes_input():
    """The browser enables Send on greeting_done, so the update goes out before
    the session opens to input."""

    async def go():
        holder: dict = {}
        room = AttributeRoom(userdata_probe=lambda: holder["userdata"])
        session = GreetSession(FakeHandle())
        session.agent_state = "listening"
        agent = GreetAgent()
        userdata = SessionUserdata(channel=Channel.inbound_chat, room=room)
        holder["userdata"] = userdata
        await entrypoint._mark_greeting_done(session, agent, userdata, room)
        assert room.updates == [{"greeting_done": "1"}]
        assert room.open_at_update == [False]
        assert userdata.greeting_done

    asyncio.run(go())


def test_a_failed_greeting_still_unlocks_the_session():
    async def go():
        for handle in (
            FakeHandle(error=RuntimeError("tts down")),
            FakeHandle(raises=RuntimeError("playout broke")),
        ):
            room = AttributeRoom()
            session, agent, userdata = await _greet(handle, room=room)
            assert userdata.greeting_done
            assert agent.greeting_done_calls == 1
            assert room.attributes["greeting_done"] == "1"

    asyncio.run(go())


def test_phone_call_greeting_unlocks_without_a_room_and_survives_a_closed_session():
    async def go():
        session, agent, userdata = await _greet(FakeHandle(), closed=True)
        assert session.replies[0]["allow_interruptions"] is False
        assert userdata.greeting_done
        assert agent.greeting_done_calls == 1

    asyncio.run(go())


def test_a_default_greeting_is_a_canned_line_without_the_llm(monkeypatch):
    pools: list[tuple] = []

    def choice(lines):
        pools.append(tuple(lines))
        return lines[-1]

    monkeypatch.setattr(entrypoint.random, "choice", choice)

    async def go():
        config = agent_config_service.resolve(None)
        values = {"agent_name": config.assistant_name, "operator_name": config.operator_name, "customer_name": ""}
        session, _, _ = await _greet(FakeHandle())
        (reply,) = session.replies
        assert reply["kind"] == "say"
        assert pools == [SPOKEN_GREETINGS_INBOUND]
        assert reply["text"] == SPOKEN_GREETINGS_INBOUND[-1].format(**values)

    asyncio.run(go())


def test_a_customised_greeting_still_goes_through_the_llm():
    async def go():
        config = agent_config_service.resolve(None)
        config.greeting_inbound = "Greet the customer as {agent_name}."
        session, _, _ = await _greet(FakeHandle(), config=config)
        (reply,) = session.replies
        assert reply["kind"] == "generate_reply"
        assert reply["instructions"] == (
            f"Greet the customer as {config.assistant_name}.\n{SALAM_INSTRUCTION}"
        )

    asyncio.run(go())


def test_every_canned_greeting_opens_with_the_salam():
    assert all(line.startswith(SALAM) for line in SPOKEN_GREETINGS_INBOUND)
