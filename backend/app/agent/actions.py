"""The OTP-gated write flow (spec 4.2): preview -> code -> confirm.

`start_action` quotes the write, issues a code bound to a new action id and
shows it on the customer's screen (`telco.otp_sms`) with a confirm card
(`telco.confirm`). `confirm_action` (voice `verify_otp` or the card's RPC)
checks the code and executes; `cancel_action` drops it. One pending write per
session: a new one replaces it. All three raise BssError; callers map it.

Start and confirm finish even when their caller is cancelled (barge-in, session
shutdown, RPC timeout): the DB work runs in a thread that commits anyway, so
the session's action state must still follow it."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, TypeVar
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.agent.telco_format import format_amount, format_day
from app.agent.tools._common import run_db
from app.agent.topics import ACCOUNT_CHANGED, CONFIRM, OTP_SMS, publish
from app.agent.userdata import SessionUserdata
from app.bss import accounts, otp, packages, recharge, rewards
from app.bss.clock import utc_now
from app.bss.errors import (
    NoPendingAction,
    OtpAttemptsExceeded,
    OtpExpired,
    OtpInvalid,
    SubscriberNotFound,
    TooManyCodes,
)
from app.bss.types import PurchaseRequest, RechargeRequest
from app.models.telco import Actor, CasePriority, PlanType, TxnChannel
from app.services.phone_numbers import spoken_digits_in_text

ActionKind = Literal["purchase", "recharge", "redeem"]

_SNAPSHOT_NOTE = "These figures replace the account snapshot in your instructions."
# A finished write ends the task: the reply closes with an offer of more help.
_DONE_NEXT = (
    "Tell them it went through briefly, then end the reply by asking whether they need help "
    "with anything else, in varied words."
)
_CODE_SENT = (
    "A 6-digit code was sent to the customer's screen; they can say or type it, or enter it "
    "on the confirm card. State the price and how they pay, then ask for the code in one short "
    "sentence, worded differently from any earlier ask in this call; naming one way is enough. "
    "In Bangla, say it the way people talk, with the English words they use (কোড, এসএমএস, "
    "কনফার্ম, টাইপ), not a translated or bookish line such as \"কেনার অনুরোধ হয়েছে\". "
    'For example: "{example}" Never read the code aloud.'
)
# Example asks, one per OTP, never the same twice in a row.
_CODE_ASKS = (
    "কোডটা বললেই কনফার্ম করে দিচ্ছি।",
    "এসএমএসে যে কোডটা পেয়েছেন, ওটা বলুন বা টাইপ করুন।",
    "স্ক্রিনের কোডটা বলুন, চাইলে কার্ডেও দিতে পারেন।",
    "কোডটা পেয়েছেন? বললেই হয়ে যাবে।",
    "কনফার্ম করতে এসএমএসের কোডটা বলুন প্লিজ।",
    "কোডটা কার্ডে দিন, অথবা আমাকে বলুন।",
)


def _code_sent(userdata: SessionUserdata) -> str:
    example = random.choice([a for a in _CODE_ASKS if a != userdata.code_ask])
    userdata.code_ask = example
    return _CODE_SENT.format(example=example)

T = TypeVar("T")


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


async def _uncancellable(coro: Awaitable[T]) -> T:
    """Awaits `coro` as its own task behind a shield: cancelling the caller
    leaves it running to the end (its outcome then goes unreported)."""
    task = asyncio.ensure_future(coro)
    # Retrieve the outcome so a cancelled caller leaves no "never retrieved" noise.
    task.add_done_callback(lambda t: t.cancelled() or t.exception())
    return await asyncio.shield(task)


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
        if q.points_earned:
            text += f" Earns {q.points_earned} reward points (1 per full ৳10)."
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
    return await _uncancellable(_start(userdata, kind, request, now))


async def _start(userdata: SessionUserdata, kind: ActionKind, request, now: datetime | None) -> str:
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
            db, subscriber_id=sid, action_id=action_id, purpose=kind, payload=payload, now=now,
            actor=Actor.agent,
        )
        return summary, text, card, code

    async with userdata.action_lock:
        recent = [t for t in userdata.otp_issued_at if now - t < otp.CODE_WINDOW]
        if len(recent) >= otp.MAX_CODES_PER_WINDOW:
            raise TooManyCodes()
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
        # The last confirmed action's code no longer replays its result.
        userdata.done_action = None
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
    lines += [text, _code_sent(userdata)]
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
        if r.points_earned:
            text += (
                f" Reward points earned: {r.points_earned}; "
                f"total now {r.reward_points}."
            )
        text += " " + _balance_line(r.main_balance, r.postpaid_due, a.postpaid)
    else:
        r = rewards.execute_redeem(db, sid, a.request, **kw)
        text = (
            f"Done: redeemed {r.offer_title}. Reference {r.transaction_ref}. "
            f"Reward points left: {r.reward_points}."
        )
        if r.expires_at is not None:
            text += f" The package is active until {format_day(r.expires_at)}."
    return r.transaction_ref, f"{text}\n{_SNAPSHOT_NOTE}\n{_DONE_NEXT}"


async def confirm_action(
    userdata: SessionUserdata,
    code: str,
    *,
    action_id: UUID | None = None,
    now: datetime | None = None,
) -> str:
    # The model may pass the code as said ("nine one eight ..."): words to digits first.
    code = otp.normalise_code(spoken_digits_in_text(code))
    return await _uncancellable(_confirm(userdata, code, action_id, now))


async def _confirm(
    userdata: SessionUserdata, code: str, action_id: UUID | None, now: datetime | None
) -> str:
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
                actor=Actor.agent,
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
        except Exception:
            # The code is consumed now, and verify passes a consumed challenge
            # with any code, so the action must go whatever failed (e.g. the
            # balance changed since the quote, or the DB errored).
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
