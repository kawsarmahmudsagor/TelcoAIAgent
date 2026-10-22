"""The OTP-gated write flow (spec 4.2): preview -> code -> confirm.

`start_action` quotes the write, issues a code bound to a new action id and
shows it on the customer's screen (`telco.otp_sms`) with a confirm card
(`telco.confirm`). `confirm_action` (voice `verify_otp` or the card's RPC)
checks the code and executes; `cancel_action` drops it. One pending write per
session: a new one replaces it. All three raise BssError; callers map it."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.agent.telco_format import format_amount, format_day
from app.agent.tools._common import run_db
from app.agent.topics import ACCOUNT_CHANGED, CONFIRM, OTP_SMS, publish
from app.agent.userdata import SessionUserdata
from app.bss import accounts, otp, packages, recharge, rewards
from app.bss.clock import utc_now
from app.bss.errors import (
    BssError,
    LimitExceeded,
    NoPendingAction,
    OtpAttemptsExceeded,
    OtpExpired,
    OtpInvalid,
    SubscriberNotFound,
)
from app.bss.types import PurchaseRequest, RechargeRequest
from app.models.telco import Actor, CasePriority, PlanType, TxnChannel

ActionKind = Literal["purchase", "recharge", "redeem"]

MAX_CODES_PER_WINDOW = 5
CODE_WINDOW = timedelta(minutes=15)

_SNAPSHOT_NOTE = "These figures replace the account snapshot in your instructions."
_CODE_SENT = (
    "A 6-digit code was sent to the customer's screen. State the price and how they pay, "
    "then ask them to say or type the code, or tap Confirm. Never read the code aloud."
)
_BENGALI_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


@dataclass
class PendingAction:
    action_id: UUID
    kind: ActionKind
    request: PurchaseRequest | RechargeRequest | UUID  # UUID = offer id
    payload: dict  # what the OTP binds
    card: dict  # title, amount, pay_from, target (recharge), expires_at (ISO)
    postpaid: bool = False
    wrong_codes: int = 0


@dataclass
class CaseDraft:
    action_id: UUID
    category: str
    description: str
    priority: CasePriority


def normalise_code(raw: str) -> str:
    """Bengali digits -> ASCII; everything but digits dropped ('১২৩ ৪৫৬' -> '123456')."""
    return "".join(c for c in raw.translate(_BENGALI_DIGITS) if c in "0123456789")


def _payload(kind: ActionKind, request) -> dict:
    if kind == "redeem":
        return {"offer_id": str(request)}
    return request.model_dump(mode="json")


def _channel(c: TxnChannel) -> str:
    return "main balance" if c == TxnChannel.balance else c.value


def _quote(db: Session, sid: UUID, kind: ActionKind, request, now: datetime) -> tuple[str, dict]:
    """The preview as (fact line, card fields); raises BssError if not allowed."""
    from app.agent.tools.packages import describe_package  # tools import this module

    if kind == "purchase":
        q = packages.preview_purchase(db, sid, request)
        text = f"Quote: {describe_package(q.package)}. Paid from {_channel(q.pay_from)}."
        if q.balance_after is not None:
            text += f" Main balance after: {format_amount(q.balance_after)}."
        card = {"title": q.package.name, "amount": float(q.price), "pay_from": q.pay_from.value}
    elif kind == "recharge":
        q = recharge.preview_recharge(db, sid, request, now=now)
        whose = "their own number" if q.is_own_number else "another number"
        text = (
            f"Quote: recharge {format_amount(q.request.amount)} to {q.target_msisdn} ({whose}), "
            f"paid by {_channel(q.request.channel)}."
        )
        if q.cashback:
            text += f" Cashback: {format_amount(q.cashback)}."
        card = {
            "title": "Recharge",
            "amount": float(q.request.amount),
            "pay_from": q.request.channel.value,
            "target": q.target_msisdn,
        }
    else:
        q = rewards.preview_redeem(db, sid, request, now=now)
        text = (
            f"Quote: redeem {q.offer.title} for {q.offer.points_cost} points; "
            f"{q.points_after} points left after."
        )
        card = {
            "title": q.offer.title,
            "amount": None,
            "pay_from": "points",
            "points": q.offer.points_cost,
        }
    return text, card


async def start_action(
    userdata: SessionUserdata, kind: ActionKind, request, *, now: datetime | None = None
) -> str:
    sid = userdata.subscriber_id
    if sid is None:
        raise SubscriberNotFound()
    now = now or utc_now()
    action_id = uuid4()
    payload = _payload(kind, request)

    def prepare(db: Session):
        summary = accounts.get_account_summary(db, sid)
        text, card = _quote(db, sid, kind, request, now)
        code = otp.issue(
            db, subscriber_id=sid, action_id=action_id, purpose=kind, payload=payload, now=now
        )
        return summary, text, card, code

    async with userdata.action_lock:
        recent = [t for t in userdata.otp_issued_at if now - t < CODE_WINDOW]
        if len(recent) >= MAX_CODES_PER_WINDOW:
            raise LimitExceeded("Too many verification codes requested")
        summary, text, card, code = await run_db(prepare)
        userdata.otp_issued_at = recent + [now]
        expires_at = (now + otp.OTP_TTL).isoformat()
        card["expires_at"] = expires_at
        lines = []
        old = userdata.pending_action
        if old is not None:
            await _publish_card(userdata, old, "cancelled")
            lines.append(f"The earlier pending {old.kind} was cancelled and replaced.")
        userdata.pending_action = PendingAction(
            action_id=action_id,
            kind=kind,
            request=request,
            payload=payload,
            card=card,
            postpaid=summary.plan_type == PlanType.postpaid,
        )
        await publish(
            userdata,
            OTP_SMS,
            {
                "action_id": str(action_id),
                "code": code,
                "to": summary.masked_msisdn,
                "expires_at": expires_at,
            },
        )
        await _publish_card(userdata, userdata.pending_action, "awaiting_code")
    lines += [text, _CODE_SENT]
    return "\n".join(lines)


async def _publish_card(userdata: SessionUserdata, action: PendingAction, state: str, **extra) -> None:
    await publish(
        userdata,
        CONFIRM,
        {
            "action_id": str(action.action_id),
            "kind": action.kind,
            "state": state,
            **action.card,
            **extra,
        },
    )


def _balance_line(main, due, postpaid: bool) -> str:
    if postpaid:
        return f"Bill due now: {format_amount(due)}."
    return f"Main balance now: {format_amount(main)}."


def _execute(db: Session, sid: UUID, a: PendingAction, now: datetime) -> tuple[str, str]:
    """Runs the write; returns (transaction ref, result facts)."""
    kw = {"action_id": a.action_id, "actor": Actor.agent, "now": now}
    if a.kind == "purchase":
        r = packages.execute_purchase(db, sid, a.request, **kw)
        text = (
            f"Done: {r.package.name} is active until {format_day(r.expires_at)}. "
            f"Reference {r.transaction_ref}. "
            + _balance_line(r.main_balance, r.postpaid_due, a.postpaid)
        )
    elif a.kind == "recharge":
        r = recharge.execute_recharge(db, sid, a.request, **kw)
        text = (
            f"Done: recharged {format_amount(r.amount)} to {r.target_msisdn}. "
            f"Reference {r.transaction_ref}."
        )
        if r.cashback:
            text += f" Cashback credited: {format_amount(r.cashback)}."
        text += " " + _balance_line(r.main_balance, r.postpaid_due, a.postpaid)
    else:
        r = rewards.execute_redeem(db, sid, a.request, **kw)
        text = (
            f"Done: redeemed {r.offer_title}. Reference {r.transaction_ref}. "
            f"Reward points left: {r.reward_points}."
        )
        if r.expires_at is not None:
            text += f" The pack is active until {format_day(r.expires_at)}."
    return r.transaction_ref, f"{text}\n{_SNAPSHOT_NOTE}"


async def confirm_action(
    userdata: SessionUserdata,
    code: str,
    *,
    action_id: UUID | None = None,
    now: datetime | None = None,
) -> str:
    code = normalise_code(code)
    async with userdata.action_lock:
        a = userdata.pending_action
        if a is None or (action_id is not None and action_id != a.action_id):
            # A second confirmer (voice and card together) of the action that
            # just went through gets the same result.
            done = userdata.done_action
            if done is not None and code == done[1] and action_id in (None, done[0]):
                return done[2]
            raise NoPendingAction()
        sid = userdata.subscriber_id
        if sid is None:
            raise SubscriberNotFound()
        if len(code) != 6:
            raise OtpInvalid("Not a 6-digit code")
        now = now or utc_now()

        def verify(db: Session) -> None:
            otp.verify(
                db,
                subscriber_id=sid,
                action_id=a.action_id,
                purpose=a.kind,
                payload=a.payload,
                code=code,
                now=now,
            )

        try:
            await run_db(verify)
        except OtpExpired:
            await _drop(userdata, "expired")
            raise
        except OtpAttemptsExceeded:
            await _drop(userdata, "cancelled")
            raise
        except OtpInvalid:
            a.wrong_codes += 1
            if a.wrong_codes >= otp.MAX_ATTEMPTS:
                await _drop(userdata, "cancelled")
                raise OtpAttemptsExceeded() from None
            raise

        try:
            ref, text = await run_db(lambda db: _execute(db, sid, a, now))
        except BssError:
            # e.g. the balance changed since the quote: this action cannot go through.
            await _drop(userdata, "cancelled")
            raise
        userdata.pending_action = None
        userdata.done_action = (a.action_id, code, text)
        await _publish_card(userdata, a, "done", ref=ref)
        await publish(userdata, ACCOUNT_CHANGED, {"kind": a.kind, "ref": ref})
        return text


async def _drop(userdata: SessionUserdata, state: str) -> None:
    a = userdata.pending_action
    userdata.pending_action = None
    if a is not None:
        await _publish_card(userdata, a, state)


async def cancel_action(
    userdata: SessionUserdata, *, action_id: UUID | None = None, now: datetime | None = None
) -> str:
    async with userdata.action_lock:
        a = userdata.pending_action
        if a is None or (action_id is not None and action_id != a.action_id):
            raise NoPendingAction()
        await _drop(userdata, "cancelled")
    return f"The pending {a.kind} was cancelled; nothing was charged."
