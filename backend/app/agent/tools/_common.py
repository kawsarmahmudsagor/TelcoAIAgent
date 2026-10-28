"""Shared helpers for the telco tools: guest check, DB access off the event
loop, and fixed guidance text for every BssError (no codes or exception text
ever reach the customer)."""

import asyncio
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import TypeVar
from uuid import UUID

from livekit.agents.llm import ToolError
from sqlalchemy.orm import Session

from app.agent.userdata import SessionUserdata
from app.bss.errors import BssError, InvalidRequest, SubscriberNotFound
from app.db.session import SessionLocal

T = TypeVar("T")

NOT_LOGGED_IN = (
    "The customer is not logged in, so their account cannot be accessed. "
    "Ask them to log in to their account first."
)

_GENERIC = "Something went wrong. Apologise briefly and ask the customer to try again."

ERROR_TEXT: dict[str, str] = {
    "insufficient_balance": (
        "The main balance is too low for this. Offer to help them recharge first, then try again."
    ),
    "package_not_found": (
        "That package does not exist. Offer to search the available packages with search_packages."
    ),
    "limit_exceeded": (
        "A recharge limit was reached. A recharge must be between 20 and 1000 taka, and at most "
        "5000 taka can be recharged per day. Tell them what applies and ask them to try again later."
    ),
    "too_many_codes": (
        "Too many codes were requested. Please wait a few minutes and try again. "
        "Tell the customer this and ask them to wait a few minutes before trying again."
    ),
    "invalid_msisdn": "That is not a valid mobile number. Ask for an 11-digit number starting with 01.",
    "msisdn_taken": "That number already has an account. Suggest they log in or reset the password.",
    "otp_expired": "The code has expired and the action was cancelled. Offer to start again.",
    "otp_invalid": (
        "The code did not match. Ask them to check the SMS shown on screen and say the code again."
    ),
    "otp_attempts_exceeded": (
        "Too many wrong codes were entered and the action was cancelled. Offer to start again."
    ),
    "no_pending_action": "Nothing is waiting for a code right now. Ask what they would like to do.",
    "offer_not_eligible": (
        "The customer is not eligible for that offer. Explain this and mention other offers they can take."
    ),
    "insufficient_points": (
        "They do not have enough reward points for this. Tell them their points balance."
    ),
    "case_not_found": (
        "That support case was not found. Ask them to check the case number or describe the problem."
    ),
    "incident_not_found": (
        "That network incident was not found. It is not something the customer needs to act on."
    ),
    "notification_not_found": (
        "That notification was not found. It is not something the customer needs to act on."
    ),
    "offer_not_found": (
        "That offer was not found. It is not something the customer needs to act on."
    ),
    "offer_in_use": (
        "That offer has already been used. It is not something the customer needs to act on."
    ),
    "subscriber_not_found": NOT_LOGGED_IN,
    "invalid_request": "That request could not be processed. Ask the customer to rephrase what they want.",
}


def subscriber_id_or_none(userdata: SessionUserdata) -> UUID | None:
    return userdata.subscriber_id


def error_text(err: BssError) -> str:
    """Fixed guidance for `err`; its own message is for logs only."""
    return ERROR_TEXT.get(err.code, _GENERIC)


async def run_db(fn: Callable[[Session], T]) -> T:
    """Runs `fn(session)` in a worker thread with its own session; rolls back on
    an exception and always closes. `fn` commits for itself."""

    def _run() -> T:
        session = SessionLocal()
        try:
            return fn(session)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return await asyncio.to_thread(_run)


E = TypeVar("E", bound=Enum)


# A list tool hands the model up to LISTED items and asks it to read out
# READ_OUT at a time, so "any others?" has its answer (run_28: "2 more not
# listed" left the agent unable to say which).
READ_OUT = 3
LISTED = 10


def listed(lines: list[str], total: int) -> list[str]:
    """`lines` (one per item, in order) cut to LISTED, with how to read them
    out; past LISTED, the rest are only counted."""
    out = lines[:LISTED]
    if total > READ_OUT:
        out.append(
            f"Read out {READ_OUT} at a time; the others above are for when the customer asks "
            "for more."
        )
    if total > LISTED:
        out.append(f"{total - LISTED} more not listed; offer to narrow it down.")
    return out


def parse_enum(enum_cls: type[E], value: str | None) -> E | None:
    """The enum member named by an LLM-supplied string; unknown -> InvalidRequest."""
    if value is None or value == "":
        return None
    try:
        return enum_cls(value.strip().lower())
    except ValueError:
        raise InvalidRequest(f"unknown {enum_cls.__name__}: {value!r}") from None


async def run_read(
    userdata: SessionUserdata, fn: Callable[[Session, UUID], str], *, verify: bool = False
) -> str:
    """The shared body of an account read tool: guests (and a subscriber id
    with no row) get the log-in guidance, any other BssError becomes a
    ToolError with fixed guidance. `fn(session, subscriber_id)` returns the text.
    `verify` first checks the subscriber exists, for reads whose bss call
    would otherwise just return an empty list for an unknown id."""
    sid = subscriber_id_or_none(userdata)
    if sid is None:
        return NOT_LOGGED_IN

    def call(db: Session) -> str:
        if verify:
            from app.bss import accounts

            accounts.get_account_summary(db, sid)
        return fn(db, sid)

    try:
        return await run_db(call)
    except SubscriberNotFound:
        return NOT_LOGGED_IN
    except BssError as err:
        raise ToolError(error_text(err)) from err


async def run_write(userdata: SessionUserdata, call: Callable[[], Awaitable[str]]) -> str:
    """The shared body of a write tool: guests (and a subscriber id with no
    row) get the log-in guidance, any other BssError becomes a ToolError with
    fixed guidance."""
    if subscriber_id_or_none(userdata) is None:
        return NOT_LOGGED_IN
    try:
        return await call()
    except SubscriberNotFound:
        return NOT_LOGGED_IN
    except BssError as err:
        raise ToolError(error_text(err)) from err
