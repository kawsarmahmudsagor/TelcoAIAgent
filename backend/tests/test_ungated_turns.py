"""Ungated browser sessions publish the voice turns the agent answers, as the turn
gate does for the turns it accepts, so the browser shows only those in every
mode. The room is a fake; _build_session runs with stubbed models."""

import asyncio

import pytest
from livekit.agents import StopResponse, llm
from test_gated_session import FakeRoom
from test_greeting_guard import AttributeRoom

from app.agent import entrypoint, gated_agent
from app.agent.gated_agent import GATE_ATTRIBUTE, USER_TURN_TOPIC, TurnPublishingAgent
from app.agent.userdata import Channel, SessionUserdata
from app.config import Settings
from app.services import agent_config_service


def _msg(text: str) -> llm.ChatMessage:
    return llm.ChatMessage(role="user", content=[text], transcript_confidence=0.9)


def test_an_answered_voice_turn_is_published():
    async def go():
        room = FakeRoom()
        agent = TurnPublishingAgent(room=room, instructions="test")
        # Returns normally: the library goes on to answer the turn.
        await agent.on_user_turn_completed(llm.ChatContext.empty(), _msg(" Is parking included? "))
        assert room.sent == [(USER_TURN_TOPIC, "Is parking included?")]

    asyncio.run(go())


def test_an_empty_turn_is_not_published():
    async def go():
        room = FakeRoom()
        agent = TurnPublishingAgent(room=room, instructions="test")
        await agent.on_user_turn_completed(llm.ChatContext.empty(), _msg("   "))
        assert room.sent == []

    asyncio.run(go())


def test_a_failed_publish_never_drops_the_turn():
    class BrokenRoom(FakeRoom):
        async def send_text(self, text, *, topic):
            raise RuntimeError("data channel closed")

    async def go():
        agent = TurnPublishingAgent(room=BrokenRoom(), instructions="test")
        await agent.on_user_turn_completed(llm.ChatContext.empty(), _msg("hello"))

    asyncio.run(go())


def test_browser_sessions_announce_published_turns():
    async def go():
        room = AttributeRoom()
        await entrypoint._announce_user_turns(room)
        assert room.updates == [{GATE_ATTRIBUTE: "1"}]

    asyncio.run(go())


# ---- _build_session picks the agent ----


class _StubSession:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def on(self, event, handler):
        pass


def _build(monkeypatch, *, gate_key: str, room):
    monkeypatch.setattr(entrypoint.silero.VAD, "load", staticmethod(lambda: None))
    monkeypatch.setattr(entrypoint, "_build_stt_and_tts", lambda *a: (None, None))
    monkeypatch.setattr(entrypoint, "_build_llm", lambda *a: None)
    monkeypatch.setattr(entrypoint, "AgentSession", _StubSession)
    monkeypatch.setattr(
        entrypoint.usage_log.UsageLogger, "attach", lambda self, session: None, raising=False
    )
    userdata = SessionUserdata(channel=Channel.inbound_chat, room=room)
    config = agent_config_service.resolve(None)
    settings = Settings(_env_file=None, openrouter_api_key="or-key")
    return entrypoint._build_session(settings, userdata, config, gate_key=gate_key, room=room)


def test_ungated_browser_session_publishes_its_turns(monkeypatch):
    room = FakeRoom()
    room.name = "chat-1"
    _, agent = _build(monkeypatch, gate_key="", room=room)
    assert isinstance(agent, TurnPublishingAgent)


def test_gated_browser_session_uses_the_gate(monkeypatch):
    room = FakeRoom()
    room.name = "chat-1"

    async def go():
        return _build(monkeypatch, gate_key="or-key", room=room)

    _, agent = asyncio.run(go())
    assert isinstance(agent, gated_agent.GatedAgent)


def test_phone_session_publishes_nothing(monkeypatch):
    _, agent = _build(monkeypatch, gate_key="", room=None)
    assert type(agent) is TurnPublishingAgent

    async def go():
        await agent.on_user_turn_completed(llm.ChatContext.empty(), _msg("Is parking included?"))

    asyncio.run(go())


def test_an_ungated_sound_tag_turn_is_dropped():
    async def go():
        room = FakeRoom()
        agent = TurnPublishingAgent(room=room, instructions="test")
        with pytest.raises(StopResponse):
            await agent.on_user_turn_completed(llm.ChatContext.empty(), _msg("[clears throat]"))
        assert room.sent == []

    asyncio.run(go())


def test_an_ungated_spoken_phone_number_reaches_the_agent_as_digits():
    async def go():
        room = FakeRoom()
        agent = TurnPublishingAgent(room=room, instructions="test")
        message = _msg("number zero one seven triple zero triple zero two eight")
        await agent.on_user_turn_completed(llm.ChatContext.empty(), message)
        assert message.text_content == "number 01700000028"
        assert room.sent == [(USER_TURN_TOPIC, "number 01700000028")]

    asyncio.run(go())
