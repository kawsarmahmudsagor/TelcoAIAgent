import asyncio
import json
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.agent import topics
from app.agent.tools._common import (
    ERROR_TEXT,
    NOT_LOGGED_IN,
    error_text,
    run_db,
    subscriber_id_or_none,
)
from app.agent.userdata import Channel, SessionUserdata
from app.bss.errors import BssError, InsufficientBalance, SubscriberNotFound


def _all_subclasses(cls):
    for sub in cls.__subclasses__():
        yield sub
        yield from _all_subclasses(sub)


def test_every_bss_error_has_guidance():
    codes = {c.code for c in _all_subclasses(BssError)}
    assert codes <= ERROR_TEXT.keys()


def test_error_text_hides_internal_message():
    out = error_text(InsufficientBalance("balance 3.20 < 49"))
    assert "Traceback" not in out
    assert "3.20" not in out


def test_unknown_code_falls_back_to_generic_text():
    out = error_text(BssError("boom"))
    assert out and "boom" not in out


def test_subscriber_not_found_says_log_in():
    assert error_text(SubscriberNotFound()) == NOT_LOGGED_IN


def test_tools_without_subscriber_say_log_in():
    assert subscriber_id_or_none(SessionUserdata(channel=Channel.inbound_chat, room=None)) is None


def test_subscriber_id_returned_when_set():
    sid = uuid4()
    ud = SessionUserdata(channel=Channel.inbound_chat, room=None, subscriber_id=sid)
    assert subscriber_id_or_none(ud) == sid


def test_userdata_defaults_are_not_shared():
    a = SessionUserdata(channel=Channel.inbound_chat, room=None)
    b = SessionUserdata(channel=Channel.inbound_chat, room=None)
    a.offer_ids.append(uuid4())
    assert b.offer_ids == [] and a.action_lock is not b.action_lock
    assert a.pending_action is None and a.otp_issued_at == []


def test_run_db_runs_in_own_session():
    async def go():
        assert await run_db(lambda s: s.execute(text("select 1")).scalar()) == 1

    asyncio.run(go())


def test_run_db_propagates_exceptions():
    async def go():
        def boom(session):
            raise ValueError("x")

        with pytest.raises(ValueError):
            await run_db(boom)

    asyncio.run(go())


class _Room:
    def __init__(self, fail=False):
        self.sent = []
        self.local_participant = self
        self.fail = fail

    async def send_text(self, payload, *, topic, destination_identities=None):
        if self.fail:
            raise RuntimeError("down")
        self.sent.append((topic, payload, destination_identities))


def test_publish_sends_json_on_topic():
    async def go():
        room = _Room()
        ud = SessionUserdata(
            channel=Channel.inbound_chat,
            room=room,
            defer_cards=True,
            linked_identity=lambda: "web-user",
        )
        await topics.publish(ud, topics.OTP_SMS, {"a": 1})
        # Only the linked browser gets it: the code must not reach anyone else.
        assert room.sent == [("telco.otp_sms", json.dumps({"a": 1}), ["web-user"])]
        assert ud.pending_card is None

    asyncio.run(go())


def test_publish_without_linked_identity_sends_nothing():
    async def go():
        room = _Room()
        ud = SessionUserdata(channel=Channel.inbound_chat, room=room)
        await topics.publish(ud, topics.OTP_SMS, {"code": "123456"})
        assert room.sent == []

    asyncio.run(go())


def test_publish_swallows_send_failure():
    async def go():
        ud = SessionUserdata(
            channel=Channel.inbound_chat, room=_Room(fail=True), linked_identity=lambda: "u"
        )
        await topics.publish(ud, topics.CONFIRM, {"a": 1})

    asyncio.run(go())
