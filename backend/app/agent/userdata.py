from dataclasses import dataclass
from enum import Enum
from uuid import UUID

from livekit import rtc


class Channel(str, Enum):
    inbound_chat = "inbound_chat"


@dataclass
class SessionUserdata:
    channel: Channel
    room: rtc.Room
    # A real phone call (SIP) rather than the browser. Always False for now;
    # Phase 2 may drop it.
    is_phone_call: bool = False
    # With quick replies on, a card waits in pending_card (topic, JSON) until the
    # main model's reply starts speaking (app.agent.cards), not while a filler
    # line or the lookup is still going.
    defer_cards: bool = False
    pending_card: tuple[str, str] | None = None
    # The subscriber this session is about (from the dispatch metadata); the
    # transcript recorder links the conversation to it on close.
    subscriber_id: UUID | None = None
    # The proactive nudge that started this session, if any.
    nudge_id: UUID | None = None
    # This session's `conversations` row, once the transcript recorder made it.
    conversation_id: UUID | None = None
    # Set once the first message (the greeting) has played out; until then the
    # session ignores the customer's voice and typed text (entrypoint._greet).
    greeting_done: bool = False
    # The browser's anonymous visitor id (from the token route's dispatch
    # metadata), stored on the conversation row so the chat widget can list
    # this browser's earlier conversations.
    visitor_id: UUID | None = None
