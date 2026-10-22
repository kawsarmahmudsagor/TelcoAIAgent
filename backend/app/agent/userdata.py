import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from livekit import rtc

if TYPE_CHECKING:
    from app.agent.actions import CaseDraft, PendingAction


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
    # Telco tools. The one write awaiting an OTP, and the support case being
    # drafted (types from app.agent.actions).
    pending_action: "PendingAction | None" = None
    pending_case: "CaseDraft | None" = None
    # The last write confirmed: (action_id, code, result text), so a second
    # confirmer of it (voice and card at once) gets the same answer.
    done_action: tuple[UUID, str, str] | None = None
    # Offers shown by the last list, in order, so "the second one" resolves.
    offer_ids: list[UUID] = field(default_factory=list)
    # When each OTP was issued this session (throttle).
    otp_issued_at: list[datetime] = field(default_factory=list)
    # Serialises confirm/cancel between voice tools and the card RPCs.
    action_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # Account snapshot placed in the system prompt, the customer's name, and
    # the proactive nudge wording.
    snapshot_text: str | None = None
    customer_name: str | None = None
    nudge_text: str | None = None
