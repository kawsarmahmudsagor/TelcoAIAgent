"""The OTP-gated write flow (app.agent.actions): preview -> code -> confirm."""

import asyncio
import json
import threading
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from livekit.agents.llm import ToolError
from sqlalchemy import func, select

from app.bss import otp
from app.agent import actions
from app.agent.tools import packages as package_tools
from app.agent.tools import recharge as recharge_tools
from app.agent.tools import verify as verify_tools
from app.agent.tools._common import ERROR_TEXT
from app.agent.topics import ACCOUNT_CHANGED, CONFIRM, OTP_SMS
from app.agent.userdata import Channel, SessionUserdata
from app.bss.clock import utc_now
from app.bss.errors import NoPendingAction, OtpAttemptsExceeded, OtpExpired, OtpInvalid
from app.bss.types import PurchaseRequest
from app.models.telco import Transaction, TxnChannel


CALLER = "web-user"


class _Participant:
    def __init__(self):
        self.sent: list[tuple[str, dict]] = []

    async def send_text(self, payload, *, topic, destination_identities=None):
        assert destination_identities == [CALLER]
        self.sent.append((topic, json.loads(payload)))


def _ud(sub) -> SessionUserdata:
    room = SimpleNamespace(local_participant=_Participant())
    return SessionUserdata(
        channel=Channel.inbound_chat,
        room=room,
        subscriber_id=sub.id,
        linked_identity=lambda: CALLER,
    )


def _sent(ud) -> list[tuple[str, dict]]:
    return ud.room.local_participant.sent


def _code(ud) -> str:
    return [p for t, p in _sent(ud) if t == OTP_SMS][-1]["code"]


def _txns(world, sub) -> int:
    world.db.expire_all()
    return world.db.scalar(
        select(func.count()).select_from(Transaction).where(Transaction.subscriber_id == sub.id)
    )


def _wrong(code: str) -> str:
    return "000000" if code != "000000" else "111111"


def _buyer(world, balance="500"):
    sub = world.subscriber(main_balance=Decimal(balance))
    pkg = world.package(name="PYTEST Net 10", data_mb=10240, price=Decimal("120"))
    return sub, pkg


def _purchase(pkg) -> PurchaseRequest:
    return PurchaseRequest(package_code=pkg.code, pay_from=TxnChannel.balance)


def test_purchase_needs_code_then_executes(bss_world):
    sub, pkg = _buyer(bss_world)
    ud = _ud(sub)

    async def go():
        out = await package_tools.run_purchase_package(ud, pkg.code)
        assert _txns(bss_world, sub) == 0
        assert [t for t, _ in _sent(ud)] == [OTP_SMS, CONFIRM]
        sms, card = _sent(ud)[0][1], _sent(ud)[1][1]
        assert sms["code"] not in out and "Never read the code aloud" in out
        assert "enter it on the confirm card" in out and "tap Confirm" not in out
        assert sms["to"].endswith(sub.msisdn[-4:]) and sms["to"] != sub.msisdn
        assert card["state"] == "awaiting_code" and card["kind"] == "purchase"
        assert card["action_id"] == sms["action_id"] == str(ud.pending_action.action_id)
        assert card["title"] == "PYTEST Net 10" and card["pay_from"] == "balance"
        assert "120 taka" in out

        done = await actions.confirm_action(ud, sms["code"])
        assert _txns(bss_world, sub) == 1
        assert ud.pending_action is None
        (t1, final), (t2, changed) = _sent(ud)[-2:]
        assert t1 == CONFIRM and final["state"] == "done" and final["ref"].startswith("TXN-")
        assert t2 == ACCOUNT_CHANGED and changed == {"kind": "purchase", "ref": final["ref"]}
        assert final["ref"] in done

    asyncio.run(go())


def test_execute_refused_without_verified_code(bss_world):
    sub, pkg = _buyer(bss_world)
    ud = _ud(sub)

    async def go():
        await package_tools.run_purchase_package(ud, pkg.code)
        with pytest.raises(ToolError) as e:
            await verify_tools.run_verify_otp(ud, _wrong(_code(ud)))
        assert str(e.value) == ERROR_TEXT["otp_invalid"]
        assert _txns(bss_world, sub) == 0
        assert ud.pending_action is not None

    asyncio.run(go())


def test_verify_otp_accepts_bengali_digits_and_spaces(bss_world):
    sub, pkg = _buyer(bss_world)
    ud = _ud(sub)
    bengali = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")

    async def go():
        await package_tools.run_purchase_package(ud, pkg.code)
        code = _code(ud)
        spoken = f"{code[:3]} {code[3:]}".translate(bengali)
        out = await verify_tools.run_verify_otp(ud, spoken)
        assert "replace the account snapshot" in out
        assert _txns(bss_world, sub) == 1

    asyncio.run(go())


def test_new_write_replaces_pending_action(bss_world):
    sub, pkg = _buyer(bss_world)
    ud = _ud(sub)

    async def go():
        await package_tools.run_purchase_package(ud, pkg.code)
        a_id, a_code = ud.pending_action.action_id, _code(ud)
        out = await recharge_tools.run_start_recharge(ud, 100, "bkash")
        assert out.startswith("The earlier pending purchase was cancelled and replaced.")
        cancelled = [p for t, p in _sent(ud) if t == CONFIRM and p["action_id"] == str(a_id)]
        assert cancelled[-1]["state"] == "cancelled"
        assert ud.pending_action.kind == "recharge"
        with pytest.raises(NoPendingAction):
            await actions.confirm_action(ud, a_code, action_id=a_id)
        assert _txns(bss_world, sub) == 0

    asyncio.run(go())


def test_expired_code_cancels_action(bss_world):
    sub, pkg = _buyer(bss_world)
    ud = _ud(sub)
    t0 = utc_now()

    async def go():
        await actions.start_action(ud, "purchase", _purchase(pkg), now=t0)
        a_id = str(ud.pending_action.action_id)
        with pytest.raises(OtpExpired):
            await actions.confirm_action(ud, _code(ud), now=t0 + timedelta(minutes=4))
        assert ud.pending_action is None
        topic, card = _sent(ud)[-1]
        assert topic == CONFIRM and card["action_id"] == a_id and card["state"] == "expired"
        assert _txns(bss_world, sub) == 0

    asyncio.run(go())


def test_three_wrong_codes_cancel_action(bss_world):
    sub, pkg = _buyer(bss_world)
    ud = _ud(sub)

    async def go():
        await actions.start_action(ud, "purchase", _purchase(pkg))
        code = _code(ud)
        for _ in range(2):
            with pytest.raises(OtpInvalid):
                await actions.confirm_action(ud, _wrong(code))
            assert ud.pending_action is not None
        with pytest.raises(OtpAttemptsExceeded):
            await actions.confirm_action(ud, _wrong(code))
        assert ud.pending_action is None
        assert _sent(ud)[-1][1]["state"] == "cancelled"
        with pytest.raises(NoPendingAction):
            await actions.confirm_action(ud, code)
        assert _txns(bss_world, sub) == 0

    asyncio.run(go())


def test_code_throttle(bss_world):
    sub, pkg = _buyer(bss_world)
    ud = _ud(sub)

    async def go():
        for _ in range(otp.MAX_CODES_PER_WINDOW):
            await package_tools.run_purchase_package(ud, pkg.code)
        with pytest.raises(ToolError) as e:
            await package_tools.run_purchase_package(ud, pkg.code)
        assert str(e.value) == ERROR_TEXT["too_many_codes"]
        # Outside the window the codes no longer count.
        later = utc_now() + otp.CODE_WINDOW + timedelta(seconds=1)
        await actions.start_action(ud, "purchase", _purchase(pkg), now=later)

    asyncio.run(go())


def test_cancel_action_clears_and_publishes(bss_world):
    sub, pkg = _buyer(bss_world)
    ud = _ud(sub)

    async def go():
        await actions.start_action(ud, "purchase", _purchase(pkg))
        a_id = ud.pending_action.action_id
        out = await verify_tools.run_cancel_pending_action(ud)
        assert "cancelled" in out and ud.pending_action is None
        topic, card = _sent(ud)[-1]
        assert topic == CONFIRM and card["action_id"] == str(a_id) and card["state"] == "cancelled"
        with pytest.raises(ToolError) as e:
            await verify_tools.run_cancel_pending_action(ud)
        assert str(e.value) == ERROR_TEXT["no_pending_action"]

    asyncio.run(go())


def test_second_confirm_of_done_action_replays_result(bss_world):
    sub, pkg = _buyer(bss_world)
    ud = _ud(sub)

    async def go():
        await actions.start_action(ud, "purchase", _purchase(pkg))
        a_id, code = ud.pending_action.action_id, _code(ud)
        first = await actions.confirm_action(ud, code)
        assert await actions.confirm_action(ud, code, action_id=a_id) == first
        with pytest.raises(NoPendingAction):
            await actions.confirm_action(ud, _wrong(code), action_id=a_id)
        assert _txns(bss_world, sub) == 1

    asyncio.run(go())


def test_failed_execute_drops_action_so_no_code_can_run_it(bss_world, monkeypatch):
    sub, pkg = _buyer(bss_world)
    ud = _ud(sub)

    def boom(*a, **k):
        raise RuntimeError("db down")

    async def go():
        await actions.start_action(ud, "purchase", _purchase(pkg))
        code = _code(ud)
        monkeypatch.setattr(actions, "_execute", boom)
        with pytest.raises(RuntimeError):
            await actions.confirm_action(ud, code)
        monkeypatch.undo()
        assert ud.pending_action is None
        assert _sent(ud)[-1][1]["state"] == "cancelled"
        with pytest.raises(NoPendingAction):
            await actions.confirm_action(ud, _wrong(code))
        assert _txns(bss_world, sub) == 0

    asyncio.run(go())


def test_cancelled_confirm_still_settles_the_action(bss_world, monkeypatch):
    """Barge-in or shutdown cancels the tool task between verify and execute;
    the write still commits in its thread, so the action state must follow it."""
    sub, pkg = _buyer(bss_world)
    ud = _ud(sub)
    entered, release = threading.Event(), threading.Event()
    real_execute = actions._execute

    def slow_execute(*a, **k):
        entered.set()
        release.wait(5)
        return real_execute(*a, **k)

    async def go():
        await actions.start_action(ud, "purchase", _purchase(pkg))
        a_id, code = ud.pending_action.action_id, _code(ud)
        monkeypatch.setattr(actions, "_execute", slow_execute)
        caller = asyncio.ensure_future(actions.confirm_action(ud, code))
        assert await asyncio.to_thread(entered.wait, 5)
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller
        release.set()
        async with ud.action_lock:  # the shielded confirm holds it until settled
            pass
        monkeypatch.undo()
        assert ud.pending_action is None
        cards = [p for t, p in _sent(ud) if t == CONFIRM and p["action_id"] == str(a_id)]
        assert cards[-1]["state"] == "done"
        assert _sent(ud)[-1][0] == ACCOUNT_CHANGED
        with pytest.raises(NoPendingAction):
            await actions.confirm_action(ud, _wrong(code))
        assert _txns(bss_world, sub) == 1

    asyncio.run(go())


def test_done_action_not_replayed_after_a_new_action(bss_world):
    sub, pkg = _buyer(bss_world)
    ud = _ud(sub)

    async def go():
        await actions.start_action(ud, "purchase", _purchase(pkg))
        a_id, a_code = ud.pending_action.action_id, _code(ud)
        await actions.confirm_action(ud, a_code)
        await actions.start_action(ud, "purchase", _purchase(pkg))
        await actions.cancel_action(ud)
        with pytest.raises(NoPendingAction):
            await actions.confirm_action(ud, a_code, action_id=a_id)
        with pytest.raises(NoPendingAction):
            await actions.confirm_action(ud, a_code)

    asyncio.run(go())


def test_throttle_text_differs_from_limit_text():
    assert ERROR_TEXT["too_many_codes"] != ERROR_TEXT["limit_exceeded"]
    assert "codes" not in ERROR_TEXT["limit_exceeded"].lower()
    assert "Too many codes were requested. Please wait a few minutes and try again." in (
        ERROR_TEXT["too_many_codes"]
    )
