import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from livekit import rtc

from app.agent import client_history
from app.agent.userdata import Channel, SessionUserdata, UpcomingViewing
from app.db.session import SessionLocal
from app.repositories import booking_repo, client_repo

logger = logging.getLogger("agent.session_context")


def resolve(raw_metadata: str | None, room: rtc.Room) -> SessionUserdata:
    """Parses LiveKit job/room metadata (set by the token/dispatch caller) into
    a SessionUserdata. Falls back to an anonymous inbound chat session if
    metadata is missing/malformed, so a customer connecting without any
    special setup still gets a working session."""
    try:
        meta = json.loads(raw_metadata) if raw_metadata else {}
    except json.JSONDecodeError:
        meta = {}

    channel = Channel(meta.get("channel", Channel.inbound_chat.value))
    client_id = meta.get("client_id")
    call_schedule_id = meta.get("call_schedule_id")

    client = None
    history: client_history.ClientHistory | None = None
    upcoming: UpcomingViewing | None = None
    if client_id:
        db = SessionLocal()
        try:
            client = client_repo.get(db, UUID(client_id))
            if client is not None:
                db.expunge(client)  # detach so it's usable after the session closes
                try:
                    history = client_history.load(db, client.id)
                except Exception:
                    # The call goes ahead without memory rather than not at all.
                    logger.exception("could not load conversation history of client %s", client.id)
                if channel == Channel.outbound_coldcall:
                    upcoming = _upcoming_viewing(db, client.id)
        finally:
            db.close()

    is_phone_call = bool(meta.get("dial_number"))
    visitor_id = (
        parse_visitor_id(meta.get("visitor_id"))
        if channel == Channel.inbound_chat and not is_phone_call
        else None
    )

    return SessionUserdata(
        channel=channel,
        room=room,
        client=client,
        client_id=client.id if client is not None else None,
        call_schedule_id=UUID(call_schedule_id) if call_schedule_id else None,
        is_phone_call=is_phone_call,
        history=history,
        visitor_id=visitor_id,
        upcoming_viewing=upcoming,
    )


def _upcoming_viewing(db, client_id: UUID) -> UpcomingViewing | None:
    """The viewing a cold call follows up; None if there is none or it can't
    be read (the call then runs as a plain cold call)."""
    try:
        row = booking_repo.next_upcoming_for_client(db, client_id, datetime.now(timezone.utc))
    except Exception:
        logger.exception("could not load the upcoming viewing of client %s", client_id)
        return None
    if row is None:
        return None
    booking, prop = row
    return UpcomingViewing(
        booking_id=booking.id,
        when=booking.proposed_datetime,
        property_title=prop.title if prop is not None else None,
    )


def parse_visitor_id(raw: object) -> UUID | None:
    """The browser's visitor id if it is a well-formed UUID string, else None
    (a bad value just means the conversation isn't listed in its history)."""
    if not isinstance(raw, str) or len(raw) > 64:
        return None
    try:
        return UUID(raw)
    except ValueError:
        return None
