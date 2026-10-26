"""A guest session upgraded to the customer who logged in mid-conversation:
the server writes the subscriber into the room metadata, and the agent takes
the account without restarting the conversation. Only a guest is upgraded."""

import asyncio
import json
import uuid
from dataclasses import replace
from decimal import Decimal

from sqlalchemy import select

from app.agent import account_link
from app.agent.account_link import ACCOUNT_ATTRIBUTE, AccountLink, parse_link
from app.agent import voice_mode
from app.agent.prompt_defaults import CHANNEL_TEXT_NOTE, LOGIN_FOLLOWUP
from app.agent.snapshot import GUEST_SNAPSHOT
from app.agent.userdata import Channel, SessionUserdata
from app.agent.voice_mode import VOICE_ATTRIBUTE, VoiceMode
from app.models.conversation import Conversation
from app.repositories import conversation_repo
from app.services import agent_config_service


class FakeRoom:
    def __init__(self):
        self.handlers = {}
        self.attributes: dict[str, str] = {}
        self.local_participant = self

    def on(self, event, handler):
        self.handlers[event] = handler

    async def set_attributes(self, attributes):
        self.attributes.update(attributes)


class FakeAudioSwitch:
    def __init__(self):
        self.calls: list[bool] = []

    def set_audio_enabled(self, enabled):
        self.calls.append(enabled)


class FakeSession:
    def __init__(self):
        self.replies: list[str] = []
        self.input = FakeAudioSwitch()
        self.output = FakeAudioSwitch()

    def generate_reply(self, *, instructions):
        self.replies.append(instructions)


class FakeAgent:
    def __init__(self, instructions):
        self.instructions = instructions

    async def update_instructions(self, instructions):
        self.instructions = instructions


PROMPT = f"IDENTITY\n{GUEST_SNAPSHOT}\n\nTASK"


def _link(subscriber_id=None, conversation_id=None, *, voice_replies=True, prompt=PROMPT):
    room, session = FakeRoom(), FakeSession()
    agent = FakeAgent(prompt)
    config = replace(agent_config_service.resolve(None), voice_replies_enabled=voice_replies)
    userdata = SessionUserdata(channel=Channel.inbound_chat, room=None)
    userdata.subscriber_id = subscriber_id
    userdata.snapshot_text = GUEST_SNAPSHOT
    userdata.conversation_id = conversation_id
    link = AccountLink(session=session, agent=agent, userdata=userdata, room=room, config=config)
    link.attach()
    return link, room, session, agent, userdata


def test_parse_link_accepts_only_a_subscriber_uuid():
    sid = uuid.uuid4()
    assert parse_link(json.dumps({"subscriber_id": str(sid)})) == sid
    for bad in (None, "", "not json", "[]", json.dumps({"subscriber_id": "x"}), "{}"):
        assert parse_link(bad) is None, bad


def test_a_guest_is_upgraded_in_place(bss_world):
    sub = bss_world.subscriber(full_name="Samiha Khan", main_balance=Decimal("486.50"))
    conversation = conversation_repo.create(
        bss_world.db, channel="inbound_chat", room_name="pytest-link", subscriber_id=None,
        is_phone_call=False, visitor_id=None,
    )

    async def go():
        link, room, session, agent, userdata = _link(conversation_id=conversation.id)
        assert await link.link(sub.id) is True
        assert userdata.subscriber_id == sub.id and userdata.customer_name == "Samiha"
        assert GUEST_SNAPSHOT not in agent.instructions
        assert "486.50" in agent.instructions and agent.instructions.startswith("IDENTITY\n")
        assert userdata.snapshot_text in agent.instructions
        assert room.attributes[ACCOUNT_ATTRIBUTE] == str(sub.id)
        assert session.replies == [LOGIN_FOLLOWUP]

    try:
        asyncio.run(go())
        bss_world.db.expire_all()
        row = bss_world.db.scalar(select(Conversation).where(Conversation.id == conversation.id))
        assert row.subscriber_id == sub.id
    finally:
        bss_world.db.delete(bss_world.db.get(Conversation, conversation.id))
        bss_world.db.commit()


def test_a_customer_session_is_never_switched(bss_world):
    other = bss_world.subscriber(full_name="Rafi Ahmed")

    async def go():
        owner = uuid.uuid4()
        link, room, session, agent, userdata = _link(subscriber_id=owner)
        assert await link.link(other.id) is False
        assert userdata.subscriber_id == owner and agent.instructions == PROMPT
        assert session.replies == [] and room.attributes == {}

    asyncio.run(go())


def test_an_unknown_subscriber_leaves_the_guest_alone(db):
    async def go():
        link, _, session, agent, userdata = _link()
        assert await link.link(uuid.uuid4()) is False
        assert userdata.subscriber_id is None and agent.instructions == PROMPT
        assert session.replies == []

    asyncio.run(go())


def test_the_room_metadata_event_triggers_one_upgrade(monkeypatch):
    calls = []

    async def fake_link(self, subscriber_id):
        calls.append(subscriber_id)
        return True

    monkeypatch.setattr(account_link.AccountLink, "link", fake_link)

    async def go():
        _, room, *_ = _link()
        sid = uuid.uuid4()
        handler = room.handlers["room_metadata_changed"]
        handler("", json.dumps({"subscriber_id": str(sid)}))
        handler("", "garbage")
        for _ in range(5):
            await asyncio.sleep(0)
        assert calls == [sid]

    asyncio.run(go())


def test_publish_account_marks_guest_and_customer():
    async def go():
        room = FakeRoom()
        userdata = SessionUserdata(channel=Channel.inbound_chat, room=None)
        await account_link.publish_account(room, userdata)
        assert room.attributes == {ACCOUNT_ATTRIBUTE: ""}
        userdata.subscriber_id = uuid.uuid4()
        await account_link.publish_account(room, userdata)
        assert room.attributes == {ACCOUNT_ATTRIBUTE: str(userdata.subscriber_id)}

    asyncio.run(go())


GUEST_PROMPT = f"{PROMPT}\n\n{CHANNEL_TEXT_NOTE}"


def _guest_link(bss_world, *, voice_replies):
    sub = bss_world.subscriber(full_name="Nusrat Jahan")
    link, room, session, agent, userdata = _link(voice_replies=voice_replies, prompt=GUEST_PROMPT)
    userdata.voice_mode = VoiceMode.off
    return sub, link, room, session, agent, userdata


def test_upgrade_turns_voice_on(bss_world):
    sub, link, room, session, agent, userdata = _guest_link(bss_world, voice_replies=True)

    async def go():
        assert await link.link(sub.id) is True
        assert userdata.voice_mode is VoiceMode.full
        assert room.attributes[VOICE_ATTRIBUTE] == "full"
        assert session.input.calls == [True] and session.output.calls == [True]
        assert CHANNEL_TEXT_NOTE not in agent.instructions

    asyncio.run(go())


def test_upgrade_with_voice_replies_off(bss_world):
    sub, link, room, session, agent, userdata = _guest_link(bss_world, voice_replies=False)

    async def go():
        assert await link.link(sub.id) is True
        assert userdata.voice_mode is VoiceMode.text_reply
        assert room.attributes[VOICE_ATTRIBUTE] == "text_reply"
        assert session.input.calls == [True] and session.output.calls == [False]
        assert agent.instructions.count(CHANNEL_TEXT_NOTE) == 1

    asyncio.run(go())


def test_upgrade_survives_apply_failure(bss_world, monkeypatch):
    sub, link, room, session, agent, userdata = _guest_link(bss_world, voice_replies=True)

    async def broken(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(voice_mode, "apply", broken)

    async def go():
        assert await link.link(sub.id) is True
        assert userdata.subscriber_id == sub.id
        assert userdata.voice_mode is VoiceMode.off
        assert session.replies == [LOGIN_FOLLOWUP]

    asyncio.run(go())
