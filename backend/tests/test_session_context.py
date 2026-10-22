import json
from uuid import uuid4

from app.agent.session_context import resolve
from app.agent.userdata import Channel


class FakeRoom:
    pass


def test_resolve_reads_subscriber_and_nudge():
    sid, nid = uuid4(), uuid4()
    u = resolve(json.dumps({"subscriber_id": str(sid), "nudge_id": str(nid)}), room=FakeRoom())
    assert u.subscriber_id == sid and u.nudge_id == nid and u.channel == Channel.inbound_chat


def test_resolve_bad_ids_become_none():
    u = resolve(json.dumps({"subscriber_id": "nope", "nudge_id": 7}), room=FakeRoom())
    assert u.subscriber_id is None and u.nudge_id is None


def test_resolve_no_metadata_is_anonymous_chat():
    assert resolve(None, room=FakeRoom()).subscriber_id is None
