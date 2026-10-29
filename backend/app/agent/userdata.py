import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from livekit import rtc

if TYPE_CHECKING:
    from app.agent.actions import CaseDraft, PendingAction
    from app.agent.voice_mode import VoiceMode


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
    # Set by app.agent.voice_mode.apply once the session runs; None before.
    voice_mode: "VoiceMode | None" = None
    pending_card: tuple[str, str] | None = None
    # The package card set last sent (JSON), so the same set isn't shown twice
    # in a row, and the customer's latest turn, which narrows the next set.
    shown_packages: str = ""
    turn_text: str = ""
    # The customer is closing the topic with this turn (the turn judge, or
    # app.agent.closing_offer.acknowledges): the reply offers more help.
    wrap_up: bool = False
    # The subscriber this session is about (from the dispatch metadata); the
    # transcript recorder links the conversation to it on close.
    subscriber_id: UUID | None = None
    # The proactive nudge that started this session, if any.
    nudge_id: UUID | None = None
    # The browser opened this session with a typed message: no greeting, the
    # agent answers that message straight away (a nudge session still greets).
    text_start: bool = False
    # This session's `conversations` row, once the transcript recorder made it.
    conversation_id: UUID | None = None
    # An earlier conversation the browser picked from its chat history to carry
    # on: the agent starts with its messages (resume_history, (role, text) pairs)
    # and the recorder appends to that row instead of making one. Cleared when it
    # isn't this customer's to reopen.
    resume_conversation_id: UUID | None = None
    resume_history: list[tuple[str, str]] = field(default_factory=list)
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
    # One action id for the whole session's human-agent handoff, so a repeat
    # request returns the same case instead of opening another.
    handoff_action_id: UUID | None = None
    # The last write confirmed: (action_id, code, result text), so a second
    # confirmer of it (voice and card at once) gets the same answer.
    done_action: tuple[UUID, str, str] | None = None
    # Offers shown by the last list, in order, so "the second one" resolves.
    offer_ids: list[UUID] = field(default_factory=list)
    # When each OTP was issued this session (throttle).
    otp_issued_at: list[datetime] = field(default_factory=list)
    # The example code ask given with the last OTP, so the next one differs.
    code_ask: str = ""
    # The identity of the browser this session talks to (entrypoint's
    # _linked_identity); telco topics are sent to it alone, so the OTP code
    # never reaches anyone else in the room.
    linked_identity: Callable[[], str | None] | None = None
    # Serialises confirm/cancel between voice tools and the card RPCs.
    action_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # Account snapshot placed in the system prompt, the customer's name, and
    # the proactive nudge wording.
    snapshot_text: str | None = None
    customer_name: str | None = None
    nudge_text: str | None = None
