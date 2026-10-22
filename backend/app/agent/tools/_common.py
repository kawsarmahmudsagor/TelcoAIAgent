"""Shared helpers for the telco tools: guest check, DB access off the event
loop, and fixed guidance text for every BssError (no codes or exception text
ever reach the customer)."""

import asyncio
from collections.abc import Callable
from typing import TypeVar
from uuid import UUID

from sqlalchemy.orm import Session

from app.agent.userdata import SessionUserdata
from app.bss.errors import BssError
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
        "A limit was reached. A recharge must be between 20 and 1000 taka, and at most 5000 taka "
        "can be recharged per day. This also applies when too many codes were requested. "
        "Tell them what applies and ask them to try again later."
    ),
    "invalid_msisdn": "That is not a valid mobile number. Ask for an 11-digit number starting with 01.",
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
