"""Dials a scheduled cold call out to a real phone over SIP (Twilio Elastic SIP
Trunk via self-hosted livekit-sip). The phone joins the call's room as one more
participant, so the agent itself is the same as for a browser call."""

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from livekit import api
from livekit.agents import JobContext

from app.agent.userdata import Channel
from app.config import Settings
from app.db.session import SessionLocal
from app.models.call_schedule import CallStatus
from app.repositories import call_schedule_repo
from app.services.phone_numbers import is_dial_allowed

logger = logging.getLogger("agent.phone_dial")

_LIVE_STATUSES = {CallStatus.dispatched, CallStatus.in_progress}


@dataclass(frozen=True)
class RingingCall:
    call_schedule_id: uuid.UUID
    # None -> the dashboard's browser is expected to join; set -> dial this phone.
    dial_number: str | None


def parse_ringing_call(raw_metadata: str | None) -> RingingCall | None:
    """The outbound cold call described by the job metadata, readable *before*
    anyone joins (session_context.resolve needs a joined room). None for
    inbound chat or malformed metadata."""
    try:
        meta = json.loads(raw_metadata) if raw_metadata else {}
    except json.JSONDecodeError:
        return None
    if meta.get("channel") != Channel.outbound_coldcall.value or not meta.get("call_schedule_id"):
        return None
    return RingingCall(
        call_schedule_id=uuid.UUID(meta["call_schedule_id"]),
        dial_number=meta.get("dial_number") or None,
    )


def phone_identity(call_schedule_id: uuid.UUID) -> str:
    return f"phone-{call_schedule_id}"


def classify_sip_failure(sip_status_code: int | None) -> tuple[CallStatus, str]:
    """Maps the SIP response a dial attempt failed with to how the call ended."""
    if sip_status_code == 486:
        return CallStatus.missed, "busy"
    if sip_status_code == 603:
        return CallStatus.cancelled, "declined"
    if sip_status_code in (408, 480, 487):
        return CallStatus.missed, "no answer"
    if sip_status_code == 403:
        return CallStatus.failed, "rejected by carrier (check Geo Permissions/credentials)"
    return CallStatus.failed, f"telephony error: {sip_status_code}"


def record_call_end(call_schedule_id: uuid.UUID, status: CallStatus, outcome: str) -> None:
    """No-op if the call already reached a terminal status (e.g. hung up from
    the dashboard while ringing)."""
    db = SessionLocal()
    try:
        call_schedule_repo.transition(
            db,
            call_schedule_id,
            from_statuses=_LIVE_STATUSES,
            values={"status": status, "outcome": outcome, "completed_at": datetime.now(timezone.utc)},
        )
    finally:
        db.close()


def _entry_still_dialable(call_schedule_id: uuid.UUID, number: str) -> bool:
    """The row may have been cancelled, deleted, or failed by the scheduler
    since this job was dispatched -- never ring a phone for a dead call."""
    db = SessionLocal()
    try:
        entry = call_schedule_repo.get(db, call_schedule_id)
        return entry is not None and entry.status in _LIVE_STATUSES and entry.dial_number == number
    finally:
        db.close()


async def _hang_up(ctx: JobContext, reason: str) -> None:
    await ctx.delete_room()
    ctx.shutdown(reason=reason)


async def dial(ctx: JobContext, call_schedule_id: uuid.UUID, number: str, settings: Settings) -> bool:
    """Rings `number` and returns once it's answered (True). On any failure the
    call's status/outcome is recorded, the room torn down, the job shut down,
    and False returned."""
    if not _entry_still_dialable(call_schedule_id, number):
        logger.info("call %s is no longer live, not dialing", call_schedule_id)
        await _hang_up(ctx, "call no longer live")
        return False
    if not is_dial_allowed(number, settings):
        record_call_end(call_schedule_id, CallStatus.failed, f"{number} is not on SIP_DIAL_ALLOWLIST")
        await _hang_up(ctx, "number not allowed")
        return False

    try:
        # wait_until_answered makes the library size its own HTTP timeout to the
        # ring window, so no outer timeout here.
        await ctx.api.sip.create_sip_participant(
            api.CreateSIPParticipantRequest(
                room_name=ctx.room.name,
                sip_trunk_id=settings.sip_outbound_trunk_id,
                sip_call_to=number,
                participant_identity=phone_identity(call_schedule_id),
                wait_until_answered=True,
                ringing_timeout={"seconds": settings.sip_ring_timeout_s},
                max_call_duration={"seconds": settings.sip_max_call_duration_s},
            )
        )
    except api.SipCallError as exc:
        logger.info("call %s not answered: %s (metadata=%s)", call_schedule_id, exc, exc.metadata)
        status, outcome = classify_sip_failure(exc.sip_status_code)
        record_call_end(call_schedule_id, status, outcome)
        await _hang_up(ctx, outcome)
        return False
    except Exception as exc:
        # Trunk missing, livekit-sip/redis not running, network errors, ...
        logger.exception("dialing call %s failed", call_schedule_id)
        record_call_end(call_schedule_id, CallStatus.failed, f"telephony error: {exc}")
        await _hang_up(ctx, "telephony error")
        return False
    return True
