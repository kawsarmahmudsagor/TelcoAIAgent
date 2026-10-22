"""Booking a viewing: one form, filled by voice or typed, read back, confirmed.

`userdata.pending_booking` is the form. The LLM fills it with
update_booking_form (tools/booking_form.py); in the browser the customer can
also type their name and phone into the form card, which reaches the agent
over RPC (`BookingRpc`). Once the form is complete it moves to `review`: the
agent reads it back, and the booking is made only on a yes -- the customer's
Confirm click (RPC `booking.confirm`) or the LLM's no-argument
book_appointment. Both end in `confirm_booking`, which books from the stored
values, so the LLM never re-types a phone number.

States: collecting -> review -> booking -> booked. An edit in the browser
after review goes back to collecting (RPC `booking.edit`), so a spoken "yes"
can't book values the customer is changing.

Browser sessions get the form's state on the `booking-form` text stream after
every change; a phone call has no screen and gets none.
"""

import asyncio
import json
import logging
import uuid
from collections.abc import Callable
from datetime import datetime

from livekit import rtc
from livekit.agents.llm import ToolError

from app.agent.tools._datetime import check_viewing_hours, parse_future_local
from app.agent.userdata import BookingState, Channel, PendingBooking, SessionUserdata
from app.config import get_settings
from app.db.session import SessionLocal
from app.models.booking import BookingChannel
from app.repositories import booking_repo, client_repo, conversation_repo
from app.services import mock_email_service
from app.services.phone_numbers import bd_mobile_local, normalize_bd_mobile

logger = logging.getLogger("agent.booking")

# Must match BOOKING_FORM_TOPIC in frontend/lib/livekit-text-streams.ts.
BOOKING_FORM_TOPIC = "booking-form"
RPC_SUBMIT = "booking.submit"
RPC_EDIT = "booking.edit"
RPC_CONFIRM = "booking.confirm"

# Shown to the customer under the form's fields.
NAME_ERROR = "Please enter your name."
PHONE_ERROR = "Please enter a Bangladeshi mobile number, e.g. 01711234567."


class BookingNotReady(ToolError):
    """confirm_booking was called when the form isn't awaiting a yes."""


def _new_form(userdata: SessionUserdata) -> PendingBooking:
    pending = PendingBooking(form_id=uuid.uuid4().hex)
    client = userdata.client
    if client is not None:
        # A cold call: the lead's name and number are on file already.
        pending.full_name = (getattr(client, "full_name", None) or "").strip() or None
        if phone := getattr(client, "phone", None):
            try:
                pending.phone = normalize_bd_mobile(phone)
            except ValueError:
                pass
    return pending


def open_form(userdata: SessionUserdata) -> PendingBooking:
    """The form to fill: the open one, or a fresh one (keeping the name and
    phone) once the last one was booked."""
    pending = userdata.pending_booking
    if pending is not None and pending.state == BookingState.booking:
        raise ToolError(
            "The booking is being confirmed right now (the customer pressed Confirm). Don't "
            "change it; tell them it's being booked."
        )
    if pending is None or pending.state == BookingState.booked:
        fresh = _new_form(userdata)
        if pending is not None:
            fresh.full_name = pending.full_name
            fresh.phone = pending.phone
        pending = userdata.pending_booking = fresh
    return pending


def missing_fields(pending: PendingBooking) -> list[str]:
    missing = []
    if pending.property_id is None and not pending.property_title:
        missing.append("which property")
    if not pending.proposed_datetime:
        missing.append("the date and time")
    if not pending.full_name:
        missing.append("their name")
    if not pending.phone:
        missing.append("their mobile number")
    return missing


def _settle_state(pending: PendingBooking) -> None:
    if pending.state in (BookingState.collecting, BookingState.review):
        complete = not missing_fields(pending)
        pending.state = BookingState.review if complete else BookingState.collecting


def merge(
    userdata: SessionUserdata,
    pending: PendingBooking,
    *,
    listing_number: int | None = None,
    proposed_datetime: str | None = None,
    full_name: str | None = None,
    phone: str | None = None,
) -> dict[str, str]:
    """Validates and stores each given field; returns {field: error} for the
    ones it rejected (the valid ones are kept). Never raises for bad input."""
    errors: dict[str, str] = {}
    if proposed_datetime is not None and proposed_datetime.strip():
        try:
            when = parse_future_local(proposed_datetime.strip(), "proposed_datetime")
            check_viewing_hours(when, "proposed_datetime")
        except ToolError as exc:
            errors["proposed_datetime"] = exc.message
        else:
            pending.proposed_datetime = when.isoformat()
    if full_name is not None:
        name = " ".join(full_name.split())
        if name:
            pending.full_name = name[:255]
        else:
            errors["full_name"] = NAME_ERROR
    if phone is not None:
        try:
            pending.phone = normalize_bd_mobile(phone)
        except ValueError:
            errors["phone"] = PHONE_ERROR
    _settle_state(pending)
    pending.revision += 1
    return errors


def form_payload(pending: PendingBooking, errors: dict[str, str] | None = None) -> dict:
    return {
        "form_id": pending.form_id,
        "state": pending.state.value,
        "revision": pending.revision,
        "full_name": pending.full_name,
        "phone": bd_mobile_local(pending.phone) if pending.phone else None,
        "property_title": pending.property_title,
        "proposed_datetime": pending.proposed_datetime,
        "errors": errors or {},
    }


async def push_state(
    userdata: SessionUserdata,
    room: rtc.Room | None,
    pending: PendingBooking,
    errors: dict[str, str] | None = None,
) -> None:
    """Shows the form's current state in the browser. Not on a phone call, and
    not before the customer has chosen a day and time: the form is for their name
    and number, and appears once the viewing time is settled."""
    if room is None or userdata.is_phone_call or not pending.proposed_datetime:
        return
    try:
        await room.local_participant.send_text(
            json.dumps(form_payload(pending, errors)), topic=BOOKING_FORM_TOPIC
        )
    except Exception:
        logger.exception("could not send booking form %s", pending.form_id)


def _spoken_time(iso: str) -> str:
    when = datetime.fromisoformat(iso)
    return when.strftime("%A %d %B %Y, %H:%M")


def read_back_instruction(pending: PendingBooking, *, is_phone_call: bool) -> str:
    confirm = (
        "Only after a clear yes, call book_appointment."
        if is_phone_call
        else "They can say yes or press Confirm on the form; only after a spoken yes, call "
        "book_appointment."
    )
    return (
        f"The booking form is complete: name {pending.full_name}, phone "
        f"{bd_mobile_local(pending.phone)}, property {pending.property_title or 'not named'}, "
        f"time {_spoken_time(pending.proposed_datetime)}. Read back the name, phone number "
        "(digit by digit), property and day and time to the customer and ask them to confirm. "
        f"{confirm} If they change anything, update the form with update_booking_form."
    )


def next_step(pending: PendingBooking, *, is_phone_call: bool) -> str:
    """update_booking_form's output: what the LLM should do now."""
    if pending.state == BookingState.review:
        return read_back_instruction(pending, is_phone_call=is_phone_call)
    if not pending.proposed_datetime:
        which = "" if pending.property_title else " and which property"
        shown = "" if is_phone_call else " The booking form appears on screen once they have."
        return (
            "Saved. Say \"Okay, I will book a live viewing for you.\" (unless you already "
            f"have), then ask which day and time they'd like to visit{which}; don't ask for "
            "their name or number yet, and don't mention a form. When they say, call "
            f"update_booking_form with proposed_datetime.{shown}"
        )
    missing = ", ".join(missing_fields(pending))
    where = (
        ""
        if is_phone_call
        else " (the booking form is now on screen: they can also type their name and number "
        'into it; in Bangla say "চাইলে স্ক্রিনে দেয়া ফর্মেও এই তথ্যগুলো দিতে পারেন")'
    )
    return (
        f"Saved on the booking form. Still missing: {missing}. Ask the customer for it{where}, "
        "then call update_booking_form again. Don't repeat or approve what they just gave you "
        "(no \"11am tomorrow is fine\"): just ask. Never ask for an email address."
    )


def _not_ready(pending: PendingBooking | None) -> BookingNotReady:
    if pending is None:
        return BookingNotReady(
            "There is no booking form yet. Fill it with update_booking_form, read it back "
            "and wait for the customer's yes."
        )
    if pending.state == BookingState.booking:
        return BookingNotReady(
            "This booking is already being confirmed (the customer pressed Confirm). Don't "
            "call book_appointment again; tell them it's being booked."
        )
    if pending.state == BookingState.booked:
        return BookingNotReady(f"Already booked: {pending.summary} Don't book it again.")
    if missing := missing_fields(pending):
        return BookingNotReady(
            f"The booking form isn't complete; still missing: {', '.join(missing)}. Ask for "
            "it, fill it in with update_booking_form, read it back and wait for their yes."
        )
    return BookingNotReady(
        "The customer is changing the details on the form on screen. Wait for them to "
        "submit it, then read it back and ask them to confirm."
    )


def _book(userdata: SessionUserdata, pending: PendingBooking, when: datetime) -> uuid.UUID:
    """The database part of confirm_booking (runs in a worker thread)."""
    settings = get_settings()
    db = SessionLocal()
    try:
        client = None
        if userdata.client is not None:
            # A cold call: the booking belongs to the lead being called.
            client = client_repo.get(db, userdata.client.id)
            if client is not None and not client.phone:
                client_repo.update(db, client, {"phone": pending.phone})
        if client is None:
            client = client_repo.get_or_create_by_phone(
                db, full_name=pending.full_name, phone=pending.phone
            )
        if userdata.conversation_id is not None:
            # Linked now rather than when the session closes, so a call to this
            # client that starts while this chat is still open already sees it.
            conversation_repo.link_client(db, userdata.conversation_id, client.id)

        booking = booking_repo.create(
            db,
            client_id=client.id,
            property_id=pending.property_id,
            channel=(
                BookingChannel.outbound_coldcall
                if userdata.channel == Channel.outbound_coldcall
                else BookingChannel.inbound_chat
            ),
            proposed_datetime=when,
            call_schedule_id=userdata.call_schedule_id,
        )
        mock_email_service.send_invite(
            db,
            booking_id=booking.id,
            client_name=pending.full_name,
            client_email=client.email,
            client_phone=pending.phone,
            ceo_email=settings.ceo_email,
            property_title=pending.property_title,
            when=when,
        )
        return client.id
    finally:
        db.close()


async def confirm_booking(userdata: SessionUserdata, room: rtc.Room | None, recorder=None) -> str:
    """Books the viewing on the form. Raises BookingNotReady unless the form is
    in review; ToolError if it can no longer be booked (a time now past).
    `recorder` (a TranscriptRecorder) is given when the booking didn't come from
    the book_appointment tool, so the transcript still gets its tool row."""
    pending = userdata.pending_booking
    # Checked and claimed with no await in between: a Confirm click and a
    # spoken yes arriving together book once.
    if pending is None or pending.state != BookingState.review:
        raise _not_ready(pending)
    pending.state = BookingState.booking

    try:
        try:
            when = parse_future_local(pending.proposed_datetime, "proposed_datetime")
        except ToolError:
            # The time passed while the form waited: ask for a new one.
            pending.proposed_datetime = None
            pending.state = BookingState.collecting
            raise
        client_id = await asyncio.to_thread(_book, userdata, pending, when)
    except BaseException as exc:
        if pending.state == BookingState.booking:
            pending.state = BookingState.review
        pending.revision += 1
        if isinstance(exc, Exception):
            error = (
                exc.message
                if isinstance(exc, ToolError)
                else "Couldn't book the viewing. Please try again."
            )
            await push_state(userdata, room, pending, {"form": error})
        raise

    userdata.client_id = client_id
    if userdata.client is not None and not userdata.client.phone:
        userdata.client.phone = pending.phone
    of_property = f" of {pending.property_title}" if pending.property_title else ""
    summary = (
        f"Booked a viewing{of_property} for {pending.full_name} at {when.isoformat()}. "
        "The agency has it and will contact the customer on the number they gave. "
        "You are talking to that customer: say \"you\" (\"we'll contact you on this "
        "number\"), never their name in the third person. Don't repeat the phone number: "
        "they've just confirmed it."
    )
    pending.state = BookingState.booked
    pending.summary = summary
    pending.revision += 1

    await push_state(userdata, room, pending)
    if recorder is not None:
        recorder.record_tool("book_appointment", {}, summary)
    return summary


def _reply(ok: bool, errors: dict[str, str] | None = None) -> str:
    return json.dumps({"ok": ok, "errors": errors or {}})


class BookingRpc:
    """The browser form's RPC methods (browser sessions only). Each answers
    quickly with JSON {ok, errors} -- performRpc gives up after 15 s -- and
    never raises, so the form can show what went wrong next to the field."""

    def __init__(
        self,
        *,
        session,
        userdata: SessionUserdata,
        room: rtc.Room,
        linked_identity: Callable[[], str | None],
        recorder=None,
    ) -> None:
        self._session = session
        self._userdata = userdata
        self._room = room
        self._linked_identity = linked_identity
        self._recorder = recorder
        self._tasks: set[asyncio.Task] = set()

    def register(self) -> None:
        participant = self._room.local_participant
        participant.register_rpc_method(RPC_SUBMIT, self.submit)
        participant.register_rpc_method(RPC_EDIT, self.edit)
        participant.register_rpc_method(RPC_CONFIRM, self.confirm)

    async def submit(self, data: rtc.RpcInvocationData) -> str:
        return await self._handle(data, self._submit)

    async def edit(self, data: rtc.RpcInvocationData) -> str:
        return await self._handle(data, self._edit)

    async def confirm(self, data: rtc.RpcInvocationData) -> str:
        return await self._handle(data, self._confirm)

    async def settle(self) -> None:
        """Waits for running confirmations (tests)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def _handle(self, data: rtc.RpcInvocationData, handler) -> str:
        if data.caller_identity != self._linked_identity():
            return _reply(False, {"form": "Not allowed."})
        try:
            payload = json.loads(data.payload)
        except (TypeError, ValueError):
            payload = None
        if not isinstance(payload, dict):
            return _reply(False, {"form": "Bad request."})
        pending = self._userdata.pending_booking
        if pending is None or payload.get("form_id") != pending.form_id:
            return _reply(False, {"form": "This form is out of date."})
        try:
            return await handler(pending, payload)
        except Exception:
            logger.exception("booking form RPC failed")
            return _reply(False, {"form": "Something went wrong. Please try again."})

    def _say(self, instructions: str) -> None:
        # Not awaited: the reply plays after the RPC has answered.
        try:
            self._session.generate_reply(instructions=instructions)
        except RuntimeError:
            logger.warning("session closed; booking form reply dropped")

    async def _submit(self, pending: PendingBooking, payload: dict) -> str:
        if pending.state in (BookingState.booking, BookingState.booked):
            return _reply(False, {"form": "This viewing is already booked."})
        errors = merge(
            self._userdata,
            pending,
            full_name=str(payload.get("full_name") or ""),
            phone=str(payload.get("phone") or ""),
        )
        await push_state(self._userdata, self._room, pending, errors)
        if errors:
            return _reply(False, errors)
        if pending.state == BookingState.review:
            self._say(
                "The customer filled in their name and phone number on the booking form. "
                + read_back_instruction(pending, is_phone_call=False)
            )
        else:
            self._say(
                "The customer filled in their name and phone number on the booking form. Still "
                f"missing: {', '.join(missing_fields(pending))}. Ask them for it, then call "
                "update_booking_form."
            )
        return _reply(True)

    async def _edit(self, pending: PendingBooking, payload: dict) -> str:
        if pending.state in (BookingState.booking, BookingState.booked):
            return _reply(False, {"form": "This viewing is already booked."})
        if pending.state == BookingState.review:
            pending.state = BookingState.collecting
            pending.revision += 1
            await push_state(self._userdata, self._room, pending)
        return _reply(True)

    async def _confirm(self, pending: PendingBooking, payload: dict) -> str:
        if pending.state != BookingState.review:
            if pending.state in (BookingState.booking, BookingState.booked):
                return _reply(False, {"form": "This viewing is already booked."})
            return _reply(False, {"form": "Please submit your details first."})
        task = asyncio.ensure_future(self._confirm_and_tell())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return _reply(True)

    async def _confirm_and_tell(self) -> None:
        try:
            summary = await confirm_booking(self._userdata, self._room, self._recorder)
        except BookingNotReady as exc:
            # A spoken yes got there first.
            logger.info("Confirm click not booked: %s", exc.message)
        except ToolError as exc:
            self._say(
                "The customer pressed Confirm on the booking form, but it couldn't be booked: "
                f"{exc.message} Tell them briefly and help them fix it."
            )
        except Exception:
            logger.exception("booking from the Confirm click failed")
            self._say(
                "The customer pressed Confirm on the booking form, but booking failed because of "
                "a system problem. Apologise briefly and ask them to press Confirm again."
            )
        else:
            self._say(
                f"The customer pressed Confirm on the booking form. {summary} Tell them their "
                "viewing is booked (property, day and time) and that the team will contact them "
                "on the number they gave (without repeating it), speaking to them as \"you\". "
                "Don't call book_appointment."
            )
