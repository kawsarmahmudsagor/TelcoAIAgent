import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from livekit import api
from livekit.agents.beta.tools.end_call import EndCallTool
from livekit.agents.llm import FunctionTool
from sqlalchemy import text

from app.agent import phone_dial
from app.agent.entrypoint import _session_tools
from app.agent.persona import build_system_prompt
from app.agent.tools.schedule_followup import schedule_followup
from app.agent.tools.search_apartments import search_apartments
from app.agent.userdata import Channel, SessionUserdata
from app.config import get_settings
from app.db.session import SessionLocal
from app.models.call_schedule import CallStatus
from app.repositories import call_schedule_repo, client_repo
from app.scheduler import jobs

TEST_EMAIL = "pytest.dial@example.invalid"
MY_PHONE = "+8801711234567"


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    db = SessionLocal()
    try:
        ids = "(select id from clients where email = :e)"
        p = {"e": TEST_EMAIL}
        db.execute(text(f"delete from call_schedule where client_id in {ids}"), p)
        db.execute(text("delete from clients where email = :e"), p)
        db.commit()
    finally:
        db.close()


def _settings(allowlist: str = MY_PHONE):
    return get_settings().model_copy(
        update={"sip_dial_allowlist": allowlist, "sip_outbound_trunk_id": "ST_test"}
    )


def _entry(status: CallStatus = CallStatus.dispatched, dial_number: str | None = MY_PHONE):
    db = SessionLocal()
    try:
        client = client_repo.get_or_create_by_email(
            db, full_name="Pytest Dial", email=TEST_EMAIL, phone=None
        )
        entry = call_schedule_repo.create(
            db, client_id=client.id, scheduled_at=datetime.now(timezone.utc), dial_number=dial_number
        )
        call_schedule_repo.update_fields(db, entry, {"status": status})
        db.refresh(entry)
        db.expunge(entry)
        return entry
    finally:
        db.close()


def _get(entry_id):
    db = SessionLocal()
    try:
        return call_schedule_repo.get(db, entry_id)
    finally:
        db.close()


class FakeJobContext:
    def __init__(self, error: Exception | None = None):
        self.requests: list = []
        self.deleted_rooms = 0
        self.shutdown_reasons: list[str] = []

        async def _create_sip_participant(request):
            self.requests.append(request)
            if error is not None:
                raise error

        self.api = SimpleNamespace(sip=SimpleNamespace(create_sip_participant=_create_sip_participant))
        self.room = SimpleNamespace(name="coldcall-test")

    async def delete_room(self):
        self.deleted_rooms += 1

    def shutdown(self, reason: str = "") -> None:
        self.shutdown_reasons.append(reason)


def _sip_error(code: str | None) -> api.SipCallError:
    metadata = {"sip_status_code": code} if code is not None else {}
    return api.SipCallError("unavailable", "dial failed", status=503, metadata=metadata)


# --- metadata parsing ---------------------------------------------------------


def test_parse_phone_call_metadata():
    call_id = uuid.uuid4()
    meta = json.dumps(
        {"channel": "outbound_coldcall", "call_schedule_id": str(call_id), "dial_number": MY_PHONE}
    )
    assert phone_dial.parse_ringing_call(meta) == phone_dial.RingingCall(call_id, MY_PHONE)


def test_parse_browser_call_metadata_has_no_number():
    call_id = uuid.uuid4()
    meta = json.dumps({"channel": "outbound_coldcall", "call_schedule_id": str(call_id), "dial_number": None})
    assert phone_dial.parse_ringing_call(meta) == phone_dial.RingingCall(call_id, None)


@pytest.mark.parametrize("raw", [None, "", "{not json", json.dumps({"channel": "inbound_chat"})])
def test_parse_non_coldcall_metadata(raw):
    assert phone_dial.parse_ringing_call(raw) is None


# --- SIP failure mapping --------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "status", "outcome"),
    [
        (486, CallStatus.missed, "busy"),
        (603, CallStatus.cancelled, "declined"),
        (408, CallStatus.missed, "no answer"),
        (480, CallStatus.missed, "no answer"),
        (487, CallStatus.missed, "no answer"),
        (403, CallStatus.failed, "rejected by carrier (check Geo Permissions/credentials)"),
        (500, CallStatus.failed, "telephony error: 500"),
        (None, CallStatus.failed, "telephony error: None"),
    ],
)
def test_classify_sip_failure(code, status, outcome):
    assert phone_dial.classify_sip_failure(code) == (status, outcome)


# --- dial() ---------------------------------------------------------------------


def test_dial_answered_returns_true_with_expected_request():
    entry = _entry()
    ctx = FakeJobContext()
    assert asyncio.run(phone_dial.dial(ctx, entry.id, MY_PHONE, _settings())) is True
    (request,) = ctx.requests
    assert request.sip_call_to == MY_PHONE
    assert request.sip_trunk_id == "ST_test"
    assert request.participant_identity == f"phone-{entry.id}"
    assert request.wait_until_answered is True
    assert request.ringing_timeout.seconds == get_settings().sip_ring_timeout_s
    assert ctx.deleted_rooms == 0
    assert ctx.shutdown_reasons == []


def test_dial_busy_marks_missed_and_hangs_up():
    entry = _entry()
    ctx = FakeJobContext(error=_sip_error("486"))
    assert asyncio.run(phone_dial.dial(ctx, entry.id, MY_PHONE, _settings())) is False
    row = _get(entry.id)
    assert (row.status, row.outcome) == (CallStatus.missed, "busy")
    assert ctx.deleted_rooms == 1
    assert ctx.shutdown_reasons


def test_dial_unexpected_error_marks_failed():
    entry = _entry()
    ctx = FakeJobContext(error=RuntimeError("no trunk"))
    assert asyncio.run(phone_dial.dial(ctx, entry.id, MY_PHONE, _settings())) is False
    row = _get(entry.id)
    assert row.status == CallStatus.failed
    assert row.outcome.startswith("telephony error")
    assert ctx.deleted_rooms == 1


def test_dial_off_allowlist_never_reaches_sip():
    entry = _entry()
    ctx = FakeJobContext()
    assert asyncio.run(phone_dial.dial(ctx, entry.id, MY_PHONE, _settings(allowlist=""))) is False
    assert ctx.requests == []
    assert _get(entry.id).status == CallStatus.failed


@pytest.mark.parametrize("status", [CallStatus.cancelled, CallStatus.failed, CallStatus.completed])
def test_dial_skips_dead_call(status):
    entry = _entry(status=status)
    ctx = FakeJobContext()
    assert asyncio.run(phone_dial.dial(ctx, entry.id, MY_PHONE, _settings())) is False
    assert ctx.requests == []
    assert _get(entry.id).status == status
    assert ctx.deleted_rooms == 1


def test_dial_skips_deleted_or_mismatched_call():
    ctx = FakeJobContext()
    assert asyncio.run(phone_dial.dial(ctx, uuid.uuid4(), MY_PHONE, _settings())) is False
    entry = _entry(dial_number="+8801922345678")
    assert asyncio.run(phone_dial.dial(ctx, entry.id, MY_PHONE, _settings())) is False
    assert ctx.requests == []


# --- session wiring ---------------------------------------------------------------


def _userdata(*, is_phone_call: bool, phone: str | None = "01711-234567", room=None):
    client = SimpleNamespace(
        id=uuid.uuid4(),
        full_name="Rahim Uddin",
        email=None,
        phone=phone,
        preferred_property_type=None,
        preferred_location="Gulshan",
        budget_min=None,
        budget_max=None,
        rent_or_buy=None,
    )
    return SessionUserdata(
        channel=Channel.outbound_coldcall,
        room=room,
        client=client,
        call_schedule_id=uuid.uuid4(),
        is_phone_call=is_phone_call,
    )


def test_end_call_tool_on_phone_and_browser_calls():
    # A phone call hangs up by deleting the room; a browser call is ended by the browser.
    phone_tools = _session_tools(_userdata(is_phone_call=True))
    browser_tools = _session_tools(_userdata(is_phone_call=False))
    assert any(isinstance(t, EndCallTool) for t in phone_tools)
    assert not any(isinstance(t, EndCallTool) for t in browser_tools)
    assert [t.id for t in browser_tools if isinstance(t, FunctionTool)].count("end_call") == 1
    browser_prompt = build_system_prompt(_userdata(is_phone_call=False))
    assert "ENDING THE CALL" in browser_prompt and "end_call" in browser_prompt
    assert "ENDING THE CALL" not in build_system_prompt(_userdata(is_phone_call=True))


def test_phone_end_call_comes_first_and_its_result_asks_for_the_goodbye():
    tool = next(t for t in _session_tools(_userdata(is_phone_call=True)) if isinstance(t, EndCallTool))
    assert tool._end_instructions and "goodbye" in tool._end_instructions
    prompt = " ".join(build_system_prompt(_userdata(is_phone_call=True)).split())
    assert "call end_call on its own, with no" in prompt


def test_browser_goodbye_comes_before_end_call():
    # A wrap-up gets "anything else?" first; the goodbye comes before end_call.
    prompt = " ".join(build_system_prompt(_userdata(is_phone_call=False)).split())
    assert "ask whether they need anything else" in prompt
    assert "call end_call in that same reply, after the goodbye" in prompt
    assert "call end_call on its own" not in prompt


def test_phone_persona_has_no_screen_and_confirms_the_number_on_file():
    prompt = build_system_prompt(_userdata(is_phone_call=True))
    assert "PHONE CALL" in prompt
    assert "the number on file is 01711-234567" in prompt
    assert "end_call" in prompt
    assert "PHONE CALL" not in build_system_prompt(_userdata(is_phone_call=False))


def test_phone_persona_without_a_number_asks_for_one():
    prompt = build_system_prompt(_userdata(is_phone_call=True, phone=None))
    assert "ask for their mobile number, read it back digit by digit" in prompt
    assert "email" not in prompt.split("PHONE CALL")[1]


def test_phone_search_skips_screen_shortlist():
    sent: list = []

    async def _send_text(*args, **kwargs):
        sent.append(args)

    room = SimpleNamespace(local_participant=SimpleNamespace(send_text=_send_text))
    ctx = SimpleNamespace(userdata=_userdata(is_phone_call=True, room=room))
    result = asyncio.run(search_apartments(ctx, location="Gulshan"))
    assert sent == []
    assert result.startswith("Found")  # seed data has Gulshan listings
    assert "phone call" in result
    assert "shown on the customer's screen" not in result


def test_followup_of_phone_call_rings_same_phone():
    entry = _entry(status=CallStatus.in_progress)
    userdata = SessionUserdata(
        channel=Channel.outbound_coldcall,
        room=None,
        client=SimpleNamespace(id=entry.client_id),
        call_schedule_id=entry.id,
        is_phone_call=True,
    )
    when = (datetime.now() + timedelta(days=2)).replace(microsecond=0).isoformat()
    asyncio.run(schedule_followup(SimpleNamespace(userdata=userdata), follow_up_date=when, note="busy"))
    db = SessionLocal()
    try:
        followups = [
            e for e in call_schedule_repo.list_all(db, status=CallStatus.pending)
            if e.client_id == entry.client_id
        ]
    finally:
        db.close()
    assert [e.dial_number for e in followups] == [MY_PHONE]


# --- scheduler dispatch -------------------------------------------------------


def test_dispatch_metadata_carries_dial_number(monkeypatch):
    entry = _entry()
    created: list = []

    class FakeLiveKitAPI:
        def __init__(self, **kwargs):
            async def _create_room(request):
                created.append(request)

            self.room = SimpleNamespace(create_room=_create_room)

        async def aclose(self):
            pass

    monkeypatch.setattr(jobs, "LiveKitAPI", FakeLiveKitAPI)
    asyncio.run(jobs._dispatch_call(entry))
    (request,) = created
    metadata = json.loads(request.agents[0].metadata)
    assert metadata["dial_number"] == MY_PHONE
    assert metadata["call_schedule_id"] == str(entry.id)
    assert _get(entry.id).status == CallStatus.in_progress
