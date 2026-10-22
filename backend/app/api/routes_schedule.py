import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_db
from app.config import get_settings
from app.models.call_schedule import CallStatus
from app.repositories import agent_config_repo, booking_repo, call_schedule_repo, client_repo
from app.schemas.call_schedule import (
    CallDecline,
    CallScheduleCreate,
    CallScheduleOut,
    CallScheduleUpdate,
    CallScheduleWithClientOut,
    IncomingCallOut,
    ScheduleLeadOut,
    UpcomingViewingOut,
)
from app.schemas.client import ClientOut
from app.services import agent_config_service
from app.services.livekit_rooms import delete_room
from app.services.phone_numbers import is_dial_allowed, normalize_e164

router = APIRouter(
    prefix="/api/schedule", tags=["schedule"], dependencies=[Depends(get_current_admin)]
)


def _with_client(
    db: Session, entry, *, viewing: UpcomingViewingOut | None = None
) -> CallScheduleWithClientOut:
    client = client_repo.get(db, entry.client_id)
    entry_out = CallScheduleOut.model_validate(entry)
    return CallScheduleWithClientOut(
        **entry_out.model_dump(), client=ClientOut.model_validate(client), viewing=viewing
    )


# Calls that haven't finished: their type (cold or follow-up) can still show.
_OPEN_STATUSES = {CallStatus.pending, CallStatus.dispatched, CallStatus.in_progress}


def _followed_up_viewing(entry, viewings, now: datetime) -> UpcomingViewingOut | None:
    """The viewing an open call will follow up: the lead's first one after the
    call time (or now, for an overdue call), the way the agent picks it when
    the call starts. None = a cold call."""
    if entry.status not in _OPEN_STATUSES:
        return None
    after = max(entry.scheduled_at, now)
    for booking, prop in viewings.get(entry.client_id, ()):
        if booking.proposed_datetime > after:
            return UpcomingViewingOut(
                booking_id=booking.id,
                when=booking.proposed_datetime,
                property_title=prop.title if prop is not None else None,
            )
    return None


@router.get("", response_model=list[CallScheduleWithClientOut])
def list_schedule(
    db: Session = Depends(get_db),
    call_status: CallStatus | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list:
    entries = call_schedule_repo.list_all(db, status=call_status, limit=limit, offset=offset)
    now = datetime.now(timezone.utc)
    open_clients = {e.client_id for e in entries if e.status in _OPEN_STATUSES}
    viewings = booking_repo.upcoming_by_client(db, open_clients, now)
    return [
        _with_client(db, entry, viewing=_followed_up_viewing(entry, viewings, now))
        for entry in entries
    ]


@router.get("/leads", response_model=list[ScheduleLeadOut])
def list_schedule_leads(db: Session = Depends(get_db)) -> list:
    """Every lead a call can be scheduled for. Those with an upcoming viewing
    come first, soonest first, each with that viewing (their call follows it
    up); the rest follow by name (a plain cold call)."""
    with_viewing = booking_repo.leads_with_upcoming_viewing(db, datetime.now(timezone.utc))
    seen = {client.id for client, _, _ in with_viewing}
    rest = sorted(
        (c for c in client_repo.list_all(db, limit=1000) if c.id not in seen),
        key=lambda c: c.full_name.casefold(),
    )
    return [
        ScheduleLeadOut(
            client=ClientOut.model_validate(client),
            viewing=UpcomingViewingOut(
                booking_id=booking.id,
                when=booking.proposed_datetime,
                property_title=prop.title if prop is not None else None,
            ),
        )
        for client, booking, prop in with_viewing
    ] + [ScheduleLeadOut(client=ClientOut.model_validate(c), viewing=None) for c in rest]


@router.post("", response_model=CallScheduleOut, status_code=status.HTTP_201_CREATED)
def create_schedule_entry(payload: CallScheduleCreate, db: Session = Depends(get_db)):
    client = client_repo.get(db, payload.client_id)
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    dial_number = _validated_dial_number(payload.dial_number)
    return call_schedule_repo.create(
        db, client_id=payload.client_id, scheduled_at=payload.scheduled_at, dial_number=dial_number
    )


def _validated_dial_number(raw: str | None) -> str | None:
    """Blank means a browser call. Anything else must be a valid number on
    SIP_DIAL_ALLOWLIST with a trunk configured to dial it -- rejected here, at
    schedule time, rather than failing silently when the call comes due."""
    if raw is None or not raw.strip():
        return None
    try:
        number = normalize_e164(raw.strip())
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    settings = get_settings()
    if not is_dial_allowed(number, settings):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"{number} is not on SIP_DIAL_ALLOWLIST"
        )
    if not settings.sip_outbound_trunk_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Phone calls aren't set up: SIP_OUTBOUND_TRUNK_ID is empty"
        )
    return number


@router.patch("/{entry_id}", response_model=CallScheduleOut)
def update_schedule_entry(
    entry_id: uuid.UUID, payload: CallScheduleUpdate, db: Session = Depends(get_db)
):
    entry = call_schedule_repo.get(db, entry_id)
    if not entry:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Schedule entry not found")
    return call_schedule_repo.update_fields(db, entry, payload.model_dump(exclude_unset=True))


# in_progress only means the room exists -- the call is still ringing until the
# agent records answered_at (someone joined), which decline_call also checks.
_RINGING_STATUSES = {CallStatus.dispatched, CallStatus.in_progress}
_DECLINE_OUTCOMES = {"cancelled": "declined by callee", "missed": "no answer"}


def _reject_phone_call(entry) -> None:
    # Phone calls ring a real phone, not the browser incoming-call screen --
    # ending one from the dashboard goes through /hangup instead.
    if entry.dial_number:
        raise HTTPException(status.HTTP_409_CONFLICT, "This call rings a phone, not the browser")


@router.get("/{entry_id}/incoming", response_model=IncomingCallOut)
def get_incoming_call(entry_id: uuid.UUID, db: Session = Depends(get_db)):
    entry = call_schedule_repo.get(db, entry_id)
    if not entry:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Schedule entry not found")
    _reject_phone_call(entry)
    config = agent_config_service.resolve(agent_config_repo.get(db))
    return IncomingCallOut(
        **_with_client(db, entry).model_dump(),
        agent_display_name=config.assistant_name,
        agency_name=config.agency_name,
    )


@router.post("/{entry_id}/decline", response_model=CallScheduleOut)
async def decline_call(entry_id: uuid.UUID, payload: CallDecline, db: Session = Depends(get_db)):
    """Ends a ringing (not yet answered) cold call from the incoming-call screen,
    either because the callee declined it or because nobody answered in time.
    Refused once the call has been answered (e.g. a second dashboard tab still
    ringing after the call was picked up elsewhere), so it can't end a live call."""
    entry = call_schedule_repo.get(db, entry_id)
    if not entry:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Schedule entry not found")
    _reject_phone_call(entry)
    changed = call_schedule_repo.transition(
        db,
        entry_id,
        from_statuses=_RINGING_STATUSES,
        values={
            "status": CallStatus(payload.reason),
            "outcome": _DECLINE_OUTCOMES[payload.reason],
            "completed_at": datetime.now(timezone.utc),
        },
        unanswered_only=True,
    )
    db.refresh(entry)
    if not changed:
        if entry.answered_at is not None and entry.status in _RINGING_STATUSES:
            raise HTTPException(status.HTTP_409_CONFLICT, "Call was already answered")
        raise HTTPException(status.HTTP_409_CONFLICT, f"Call is no longer ringing ({entry.status.value})")
    # Tear the room down so the agent job waiting for someone to join exits now.
    await delete_room(entry.livekit_room_name or f"coldcall-{entry.id}")
    return entry


@router.post("/{entry_id}/hangup", response_model=CallScheduleOut)
async def hang_up_call(entry_id: uuid.UUID, db: Session = Depends(get_db)):
    """Ends a ringing or live call from the dashboard -- the only way to stop a
    phone call short of the callee hanging up. Deleting the room drops the
    phone leg and makes the agent job exit."""
    entry = call_schedule_repo.get(db, entry_id)
    if not entry:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Schedule entry not found")
    changed = call_schedule_repo.transition(
        db,
        entry_id,
        from_statuses=_RINGING_STATUSES,
        values={
            "status": CallStatus.cancelled,
            "outcome": "ended from dashboard",
            "completed_at": datetime.now(timezone.utc),
        },
    )
    db.refresh(entry)
    if not changed:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Call is not live ({entry.status.value})")
    await delete_room(entry.livekit_room_name or f"coldcall-{entry.id}")
    return entry


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule_entry(entry_id: uuid.UUID, db: Session = Depends(get_db)) -> None:
    entry = call_schedule_repo.get(db, entry_id)
    if not entry:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Schedule entry not found")
    # A still-ringing/live call would otherwise keep going (and keep billing,
    # for a phone call) with no row left to record how it ended.
    if entry.status in _RINGING_STATUSES:
        await delete_room(entry.livekit_room_name or f"coldcall-{entry.id}")
    call_schedule_repo.delete(db, entry)
