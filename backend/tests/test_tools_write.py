"""Write tools: purchase, recharge, redeem, support case, human hand-off."""

import asyncio
import json
from decimal import Decimal
from types import SimpleNamespace

import pytest
from livekit.agents.llm import ToolError
from sqlalchemy import func, select

from app.agent.quick_reply import route
from app.agent.tools import packages, recharge, rewards, support, verify
from app.agent.turn_judge import Judgement
from app.config import Settings
from app.services.agent_config_service import resolve
from app.agent.tools._common import ERROR_TEXT, NOT_LOGGED_IN
from app.agent.topics import ACCOUNT_CHANGED, CASE_CREATED, OTP_SMS
from app.agent.userdata import Channel, SessionUserdata
from app.models.telco import CasePriority, SupportCase, Transaction


class _Participant:
    def __init__(self):
        self.sent: list[tuple[str, dict]] = []

    async def send_text(self, payload, *, topic, destination_identities=None):
        self.sent.append((topic, json.loads(payload)))


def _ud(sub=None) -> SessionUserdata:
    room = SimpleNamespace(local_participant=_Participant())
    return SessionUserdata(
        channel=Channel.inbound_chat,
        room=room,
        subscriber_id=sub.id if sub else None,
        linked_identity=lambda: "web-user",
    )


def _sent(ud):
    return ud.room.local_participant.sent


def _code(ud) -> str:
    return [p for t, p in _sent(ud) if t == OTP_SMS][-1]["code"]


def _cases(world, sub) -> list[SupportCase]:
    world.db.expire_all()
    return list(world.db.scalars(select(SupportCase).where(SupportCase.subscriber_id == sub.id)))


def test_insufficient_balance_suggests_recharge(bss_world):
    sub = bss_world.subscriber(main_balance=Decimal("50"))
    pkg = bss_world.package(price=Decimal("120"))
    ud = _ud(sub)
    with pytest.raises(ToolError) as e:
        asyncio.run(packages.run_purchase_package(ud, pkg.code))
    assert "70 taka short" in str(e.value)
    assert "Offer a recharge first (start_recharge)." in str(e.value)
    assert ud.pending_action is None and _sent(ud) == []


def test_success_text_overrides_snapshot(bss_world):
    sub = bss_world.subscriber(main_balance=Decimal("486.50"))
    pkg = bss_world.package(price=Decimal("120"))
    ud = _ud(sub)
    ud.snapshot_text = "Main balance: 486.50 taka."

    async def go():
        await packages.run_purchase_package(ud, pkg.code)
        return await verify.run_verify_otp(ud, _code(ud))

    out = asyncio.run(go())
    assert "366.50 taka" in out
    assert "These figures replace the account snapshot in your instructions." in out


def test_recharge_other_number(bss_world):
    sub = bss_world.subscriber(main_balance=Decimal("10"))
    ud = _ud(sub)

    async def go():
        out = await recharge.run_start_recharge(ud, 100, "bkash", "01812345678")
        assert "01812345678" in out and "100 taka" in out
        assert ud.pending_action.card["target"] == "01812345678"
        done = await verify.run_verify_otp(ud, _code(ud))
        assert "01812345678" in done
        with pytest.raises(ToolError) as e:
            await recharge.run_start_recharge(ud, 100, "bkash", "0123")
        assert str(e.value) == ERROR_TEXT["invalid_msisdn"]

    asyncio.run(go())
    bss_world.db.expire_all()
    txn = bss_world.db.scalar(select(Transaction).where(Transaction.subscriber_id == sub.id))
    assert txn.target_msisdn == "01812345678"


def test_redeem_by_offer_number(bss_world):
    sub = bss_world.subscriber(reward_points=500)
    pkg = bss_world.package(name="PYTEST Gift Pack", data_mb=1024, validity_days=7)
    bss_world.offer(title="PYTEST Cash", cashback_percent=Decimal("5"))
    gift = bss_world.offer(title="PYTEST Gift", points_cost=200, package_id=pkg.id)
    ud = _ud(sub)

    async def go():
        with pytest.raises(ToolError, match="get_offers_and_points"):
            await rewards.run_redeem_reward(ud, 1)
        await rewards.run_get_offers_and_points(ud)
        n = ud.offer_ids.index(gift.id) + 1
        out = await rewards.run_redeem_reward(ud, n)
        assert "PYTEST Gift" in out and "200 points" in out
        done = await verify.run_verify_otp(ud, _code(ud))
        assert "Reward points left: 300" in done
        assert _sent(ud)[-1] == (ACCOUNT_CHANGED, {"kind": "redeem", "ref": _sent(ud)[-2][1]["ref"]})

    asyncio.run(go())


def test_support_case_needs_confirmation(bss_world):
    sub = bss_world.subscriber()
    ud = _ud(sub)
    args = ("recharge_not_credited", "Recharged 100 taka by bKash, not credited.")

    async def go():
        out = await support.run_create_support_case(ud, *args)
        assert "confirmed=true" in out and _cases(bss_world, sub) == []
        first = await support.run_create_support_case(ud, *args, confirmed=True)
        rows = _cases(bss_world, sub)
        assert len(rows) == 1 and rows[0].ref in first
        # The draft is cleared after the case is created: a repeat asks again.
        again = await support.run_create_support_case(ud, *args, confirmed=True)
        assert len(_cases(bss_world, sub)) == 1 and "confirmed=true" in again
        assert (ACCOUNT_CHANGED, {"kind": "case", "ref": rows[0].ref}) in _sent(ud)

    asyncio.run(go())


def test_create_case_publishes_case_created(bss_world):
    sub = bss_world.subscriber()
    ud = _ud(sub)
    args = ("slow_data", "Data is slow in Dhanmondi since morning.")

    async def go():
        await support.run_create_support_case(ud, *args)
        assert not [t for t, _ in _sent(ud) if t == CASE_CREATED]
        await support.run_create_support_case(ud, *args, confirmed=True)

    asyncio.run(go())
    row = _cases(bss_world, sub)[0]
    (payload,) = [p for t, p in _sent(ud) if t == CASE_CREATED]
    assert payload == {
        "ref": row.ref, "category": "slow_data", "priority": "normal",
        "status": row.status.value, "created_at": row.created_at.isoformat(),
    }


def test_confirmed_case_without_draft_asks_first(bss_world):
    sub = bss_world.subscriber()
    ud = _ud(sub)
    out = asyncio.run(support.run_create_support_case(ud, "other", "x", confirmed=True))
    assert "confirmed=true" in out and _cases(bss_world, sub) == []


def test_human_agent_opens_high_priority_case(bss_world):
    sub = bss_world.subscriber()
    out = asyncio.run(support.run_request_human_agent(_ud(sub), "Customer asked for a person."))
    rows = _cases(bss_world, sub)
    assert len(rows) == 1 and rows[0].priority == CasePriority.high
    assert rows[0].ref in out and "no live transfer" in out


def test_handoff_is_idempotent_per_session(bss_world):
    sub = bss_world.subscriber()
    ud = _ud(sub)

    async def go():
        first = await support.run_request_human_agent(ud, "Customer asked for a person.")
        again = await support.run_request_human_agent(ud, "Customer asked again.")
        return first, again

    first, again = asyncio.run(go())
    rows = _cases(bss_world, sub)
    assert len(rows) == 1 and rows[0].ref in first and rows[0].ref in again
    assert ud.handoff_action_id is not None


def test_pending_case_cleared_after_create(bss_world):
    sub = bss_world.subscriber()
    ud = _ud(sub)
    args = ("slow_data", "Data is slow in Dhanmondi since morning.")

    async def go():
        await support.run_create_support_case(ud, *args)
        assert ud.pending_case is not None
        await support.run_create_support_case(ud, *args, confirmed=True)

    asyncio.run(go())
    assert ud.pending_case is None and len(_cases(bss_world, sub)) == 1


def test_cancel_clears_pending_case(bss_world):
    sub = bss_world.subscriber()
    ud = _ud(sub)
    settings = Settings(_env_file=None)
    config = resolve(None, settings)
    config.quick_reply_enabled = True
    judgement = Judgement(0.9, "none", 0.99)

    async def go():
        await support.run_create_support_case(ud, "slow_data", "Data is slow.")
        assert route(judgement, ud, config, settings) is None
        return await verify.run_cancel_pending_action(ud)

    out = asyncio.run(go())
    assert "support case was cancelled" in out and _cases(bss_world, sub) == []
    assert ud.pending_case is None
    assert route(judgement, ud, config, settings) is not None


def test_human_agent_publishes_case_created(bss_world):
    sub = bss_world.subscriber()
    ud = _ud(sub)
    asyncio.run(support.run_request_human_agent(ud, "Customer asked for a person."))
    row = _cases(bss_world, sub)[0]
    (payload,) = [p for t, p in _sent(ud) if t == CASE_CREATED]
    assert payload["ref"] == row.ref and payload["priority"] == "high"
    assert any(t == ACCOUNT_CHANGED for t, _ in _sent(ud))


def test_write_tools_without_subscriber_say_log_in():
    ud = _ud()

    async def go():
        for coro in [
            packages.run_purchase_package(ud, "X"),
            recharge.run_start_recharge(ud, 100, "bkash"),
            rewards.run_redeem_reward(ud, 1),
            verify.run_verify_otp(ud, "123456"),
            verify.run_cancel_pending_action(ud),
            support.run_create_support_case(ud, "other", "x", confirmed=True),
            support.run_request_human_agent(ud, "x"),
        ]:
            assert await coro == NOT_LOGGED_IN
        assert _sent(ud) == []

    asyncio.run(go())


def test_no_transaction_before_confirm(bss_world):
    sub = bss_world.subscriber(main_balance=Decimal("10"))
    asyncio.run(recharge.run_start_recharge(_ud(sub), 100, "nagad"))
    bss_world.db.expire_all()
    count = bss_world.db.scalar(
        select(func.count()).select_from(Transaction).where(Transaction.subscriber_id == sub.id)
    )
    assert count == 0
