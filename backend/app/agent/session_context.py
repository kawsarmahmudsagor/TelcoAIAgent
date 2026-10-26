import json
from uuid import UUID

from livekit import rtc

from app.agent.userdata import Channel, SessionUserdata


def resolve(raw_metadata: str | None, room: rtc.Room) -> SessionUserdata:
    """Parses LiveKit job/room metadata (set by the token/dispatch caller) into
    a SessionUserdata. Falls back to an anonymous chat session if metadata is
    missing/malformed, so a customer connecting without any special setup still
    gets a working session. Does not touch the DB."""
    try:
        meta = json.loads(raw_metadata) if raw_metadata else {}
    except json.JSONDecodeError:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}

    return SessionUserdata(
        channel=Channel.inbound_chat,
        room=room,
        subscriber_id=parse_uuid(meta.get("subscriber_id")),
        nudge_id=parse_uuid(meta.get("nudge_id")),
        visitor_id=parse_visitor_id(meta.get("visitor_id")),
        text_start=meta.get("text_start") is True,
        resume_conversation_id=parse_uuid(meta.get("resume_conversation_id")),
    )


def parse_uuid(raw: object) -> UUID | None:
    """A UUID if raw is a well-formed UUID string, else None."""
    if not isinstance(raw, str) or len(raw) > 64:
        return None
    try:
        return UUID(raw)
    except ValueError:
        return None


def parse_visitor_id(raw: object) -> UUID | None:
    """The browser's visitor id if it is a well-formed UUID string, else None
    (a bad value just means the conversation isn't listed in its history)."""
    return parse_uuid(raw)
