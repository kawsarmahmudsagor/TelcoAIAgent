"""Voice modes: browser visitors, guests and logged-in customers alike, speak
and hear voice or text replies by the dashboard's Voice responses switch."""

import asyncio
import uuid
from dataclasses import replace

import pytest

from app.agent import voice_mode
from app.agent.persona import build_system_prompt
from app.agent.prompt_defaults import CHANNEL_TEXT_NOTE
from app.agent.snapshot import GUEST_SNAPSHOT
from app.agent.userdata import Channel, SessionUserdata
from app.agent.voice_mode import VOICE_ATTRIBUTE, VoiceMode, apply, channel_note, mode_for
from app.services import agent_config_service


class FakeRoom:
    def __init__(self):
        self.attributes: dict[str, str] = {}
        self.local_participant = self

    async def set_attributes(self, attributes):
        self.attributes.update(attributes)


class FakeAudioSwitch:
    def __init__(self):
        self.calls: list[bool] = []

    def set_audio_enabled(self, enabled):
        self.calls.append(enabled)


class FakeSession:
    def __init__(self):
        self.input = FakeAudioSwitch()
        self.output = FakeAudioSwitch()


class FakeAgent:
    def __init__(self, instructions):
        self.instructions = instructions

    async def update_instructions(self, instructions):
        self.instructions = instructions


def _config(voice_replies: bool):
    return replace(agent_config_service.resolve(None), voice_replies_enabled=voice_replies)


def _userdata(logged_in: bool, *, phone: bool = False, mode: VoiceMode | None = None):
    userdata = SessionUserdata(channel=Channel.inbound_chat, room=None, is_phone_call=phone)
    userdata.subscriber_id = uuid.uuid4() if logged_in else None
    userdata.voice_mode = mode
    return userdata


def _apply(userdata, config, instructions="PROMPT"):
    session, agent, room = FakeSession(), FakeAgent(instructions), FakeRoom()
    mode = asyncio.run(apply(session, agent, userdata, config, room))
    return mode, session, agent, room


@pytest.mark.parametrize(
    ("logged_in", "voice_replies", "phone", "expected"),
    [
        (False, True, False, VoiceMode.full),
        (False, False, False, VoiceMode.text_reply),
        (True, True, False, VoiceMode.full),
        (True, False, False, VoiceMode.text_reply),
        (False, False, True, VoiceMode.full),
    ],
)
def test_mode_for_table(logged_in, voice_replies, phone, expected):
    assert mode_for(_userdata(logged_in, phone=phone), _config(voice_replies)) is expected


def test_channel_note_only_in_text_modes():
    assert channel_note(VoiceMode.full) == ""
    assert channel_note(VoiceMode.off) == CHANNEL_TEXT_NOTE
    assert channel_note(VoiceMode.text_reply) == CHANNEL_TEXT_NOTE


def test_apply_guest_gets_full_voice():
    userdata = _userdata(False)
    mode, session, _, room = _apply(userdata, _config(True))
    assert mode is VoiceMode.full
    assert session.input.calls == [True]
    assert session.output.calls == [True]
    assert room.attributes == {VOICE_ATTRIBUTE: "full"}
    assert userdata.voice_mode is VoiceMode.full


def test_apply_guest_with_voice_replies_off_can_speak():
    mode, session, _, room = _apply(_userdata(False), _config(False))
    assert mode is VoiceMode.text_reply
    assert session.input.calls == [True]
    assert session.output.calls == [False]
    assert room.attributes == {VOICE_ATTRIBUTE: "text_reply"}


def test_apply_full_enables_both():
    mode, session, agent, room = _apply(_userdata(True), _config(True))
    assert mode is VoiceMode.full
    assert session.input.calls == [True]
    assert session.output.calls == [True]
    assert room.attributes == {VOICE_ATTRIBUTE: "full"}
    assert agent.instructions == "PROMPT"


def test_apply_text_reply():
    prompt = f"PROMPT\n\n{CHANNEL_TEXT_NOTE}"
    mode, session, agent, room = _apply(_userdata(True), _config(False), prompt)
    assert mode is VoiceMode.text_reply
    assert session.input.calls == [True]
    assert session.output.calls == [False]
    assert room.attributes == {VOICE_ATTRIBUTE: "text_reply"}
    assert agent.instructions == prompt


def test_apply_removes_note_going_to_full():
    userdata = _userdata(True, mode=VoiceMode.off)
    _, _, agent, _ = _apply(userdata, _config(True), f"PROMPT\n\n{CHANNEL_TEXT_NOTE}")
    assert agent.instructions == "PROMPT"


def test_apply_keeps_single_note_going_to_text_reply():
    userdata = _userdata(True, mode=VoiceMode.off)
    prompt = f"PROMPT\n\n{CHANNEL_TEXT_NOTE}"
    _, _, agent, _ = _apply(userdata, _config(False), prompt)
    assert agent.instructions == prompt
    assert agent.instructions.count(CHANNEL_TEXT_NOTE) == 1


def test_apply_adds_note_when_prompt_lacks_it():
    _, _, agent, _ = _apply(_userdata(False), _config(False), "PROMPT")
    assert agent.instructions == f"PROMPT\n\n{CHANNEL_TEXT_NOTE}"


def test_prompt_has_note_only_in_text_modes():
    assert CHANNEL_TEXT_NOTE in build_system_prompt(_userdata(False), _config(False))
    assert CHANNEL_TEXT_NOTE in build_system_prompt(_userdata(True), _config(False))
    assert CHANNEL_TEXT_NOTE not in build_system_prompt(_userdata(False), _config(True))
    assert CHANNEL_TEXT_NOTE not in build_system_prompt(_userdata(True), _config(True))
    assert CHANNEL_TEXT_NOTE not in build_system_prompt(
        _userdata(False, phone=True), _config(False)
    )


def test_snapshot_replaceable_with_note():
    prompt = build_system_prompt(_userdata(False), _config(False))
    assert GUEST_SNAPSHOT in prompt
    swapped = prompt.replace(GUEST_SNAPSHOT, "X", 1)
    assert swapped.endswith(f"\n\n{CHANNEL_TEXT_NOTE}")


class FlakyRoom(FakeRoom):
    """set_attributes fails the first `failures` times."""

    def __init__(self, failures):
        super().__init__()
        self.failures = failures

    async def set_attributes(self, attributes):
        if self.failures:
            self.failures -= 1
            raise RuntimeError("network")
        await super().set_attributes(attributes)


def test_apply_publish_failure_changes_no_audio():
    session, agent, room = FakeSession(), FakeAgent("PROMPT"), FlakyRoom(failures=1)
    userdata = _userdata(True, mode=VoiceMode.off)
    with pytest.raises(RuntimeError):
        asyncio.run(apply(session, agent, userdata, _config(True), room))
    assert session.input.calls == [] and session.output.calls == []
    assert userdata.voice_mode is VoiceMode.off


def test_apply_or_text_only_falls_back_to_off():
    session, agent, room = FakeSession(), FakeAgent("PROMPT"), FlakyRoom(failures=1)
    userdata = _userdata(True)
    mode = asyncio.run(
        voice_mode.apply_or_text_only(session, agent, userdata, _config(True), room)
    )
    assert mode is VoiceMode.off
    assert session.input.calls[-1] is False and session.output.calls[-1] is False
    assert userdata.voice_mode is VoiceMode.off
    assert room.attributes == {VOICE_ATTRIBUTE: "off"}


class StubAudioStream:
    def __init__(self):
        self.events: list[str] = []

    def on_attached(self):
        self.events.append("attached")

    def on_detached(self):
        self.events.append("detached")


def test_close_input_detaches_a_stream_assigned_later():
    from livekit.agents.voice.io import AgentInput

    class Session:
        input = AgentInput(video_changed=lambda: None, audio_changed=lambda: None)

    voice_mode.close_input(Session)
    stream = StubAudioStream()
    Session.input.audio = stream
    assert stream.events == ["detached"]
