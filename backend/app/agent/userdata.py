from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from livekit import rtc

from app.models.client import Client

if TYPE_CHECKING:
    from app.agent.client_history import ClientHistory


class Channel(str, Enum):
    inbound_chat = "inbound_chat"
    outbound_coldcall = "outbound_coldcall"


class BookingState(str, Enum):
    collecting = "collecting"
    review = "review"  # complete; read back to the customer, awaiting their yes
    booking = "booking"  # confirm_booking is running
    booked = "booked"


@dataclass
class PendingBooking:
    """The viewing booking form (app.agent.booking). Filled by voice through
    update_booking_form and by the browser's form through RPC; booked from
    these values, never from anything the LLM re-types."""

    form_id: str
    state: BookingState = BookingState.collecting
    property_id: UUID | None = None
    property_title: str | None = None
    # ISO 8601 with the agency offset, as parse_future_local returned it.
    proposed_datetime: str | None = None
    full_name: str | None = None
    # E.164 ("+8801711234567"), as normalize_bd_mobile returned it.
    phone: str | None = None
    # Bumped on every change, so the browser can tell rounds of review apart.
    revision: int = 0
    # book_appointment's output once booked.
    summary: str | None = None


@dataclass
class UpcomingViewing:
    """A cold-called lead's soonest booked viewing appointment (not the listing
    open on the website; that is viewing_property_id). reschedule_viewing moves
    it."""

    booking_id: UUID
    when: datetime
    property_title: str | None = None


@dataclass
class SessionUserdata:
    channel: Channel
    room: rtc.Room
    client: Client | None = None
    call_schedule_id: UUID | None = None
    # A real phone call (SIP) rather than the browser: no screen to show
    # listings on, and the agent must hang up itself.
    is_phone_call: bool = False
    # With quick replies on, a card waits in pending_card (topic, JSON) until the
    # main model's reply starts speaking (app.agent.cards), not while a filler
    # line or the lookup is still going.
    defer_cards: bool = False
    pending_card: tuple[str, str] | None = None
    # The lead this session is about: a cold call's client, or the client
    # a booking created/found during a browser chat. The transcript
    # recorder links the conversation to it on close.
    client_id: UUID | None = None
    # The client's bookings and earlier conversations
    # (app.agent.client_history.ClientHistory), for the system prompt. None for
    # an unknown customer.
    history: "ClientHistory | None" = None
    # This session's `conversations` row, once the transcript recorder made it.
    conversation_id: UUID | None = None
    # Set once the first message (the greeting) has played out; until then the
    # session ignores the customer's voice and typed text (entrypoint._greet).
    greeting_done: bool = False
    # The viewing being booked (app.agent.booking); None until the first
    # update_booking_form call.
    pending_booking: PendingBooking | None = None
    # The browser's anonymous visitor id (from the token route's dispatch
    # metadata), stored on the conversation row so the chat widget can list
    # this browser's earlier conversations. None for phone/cold calls.
    visitor_id: UUID | None = None
    # Cold calls only: the viewing this call follows up (session_context).
    upcoming_viewing: UpcomingViewing | None = None
