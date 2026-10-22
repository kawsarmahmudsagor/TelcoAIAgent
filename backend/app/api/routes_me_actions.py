"""Customer portal writes: quote + code (start), then verify + execute (confirm).

Mirrors the agent's flow (app.agent.actions): same purposes and OTP payloads,
so a code issued here is checked by the same `execute_*` guards."""

import uuid
from datetime import timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.bss_http import bss_http_error
from app.api.deps import get_current_subscriber, get_db
from app.api.routes_me import _json
from app.api.schemas_me import ActionConfirm, ActionResult, ActionStart, PortalAction
from app.bss import accounts, otp, packages, recharge, rewards
from app.bss.clock import utc_now
from app.bss.errors import BssError
from app.bss.types import PurchaseRequest, RechargeRequest
from app.models.telco import Actor

router = APIRouter(prefix="/api/me/actions", tags=["portal"])

MAX_CODES_PER_WINDOW = 5
CODE_WINDOW = timedelta(minutes=15)


def _request(action: PortalAction) -> tuple[PurchaseRequest | RechargeRequest | uuid.UUID, dict]:
    """The bss request and the payload the OTP binds (as the execute_* functions check it)."""
    if action.kind == "purchase":
        req = PurchaseRequest(package_code=action.package_code, pay_from=action.pay_from)
    elif action.kind == "recharge":
        req = RechargeRequest(
            amount=action.amount, channel=action.channel, target_msisdn=action.target_msisdn
        )
    else:
        return action.offer_id, {"offer_id": str(action.offer_id)}
    return req, req.model_dump(mode="json")


def _money(amount: Decimal) -> str:
    return f"{amount:f}" if amount != amount.to_integral_value() else f"{int(amount)}"


@router.post("/start", response_model=ActionStart)
def start(
    body: PortalAction,
    subscriber_id: uuid.UUID = Depends(get_current_subscriber),
    db: Session = Depends(get_db),
):
    now = utc_now()
    try:
        req, payload = _request(body)
        fields: dict = {"amount": None, "pay_from": None, "target": None, "points_cost": None}
        if body.kind == "purchase":
            q = packages.preview_purchase(db, subscriber_id, req)
            fields.update(title=q.package.name, amount=q.price, pay_from=q.pay_from.value)
        elif body.kind == "recharge":
            r = recharge.preview_recharge(db, subscriber_id, req, now=now)
            fields.update(
                title=f"Recharge ৳{_money(r.request.amount)}",
                amount=r.request.amount,
                pay_from=r.request.channel.value,
                target=r.target_msisdn,
            )
        else:
            o = rewards.preview_redeem(db, subscriber_id, req, now=now)
            fields.update(title=o.offer.title, pay_from="points", points_cost=o.offer.points_cost)
        if otp.issued_since(db, subscriber_id, now - CODE_WINDOW) >= MAX_CODES_PER_WINDOW:
            raise HTTPException(
                429,
                detail={
                    "code": "too_many_codes",
                    "message": "Too many verification codes requested",
                },
            )
        action_id = uuid.uuid4()
        masked = accounts.get_account_summary(db, subscriber_id).masked_msisdn
        code = otp.issue(
            db,
            subscriber_id=subscriber_id,
            action_id=action_id,
            purpose=body.kind,
            payload=payload,
            now=now,
        )
    except BssError as e:
        db.rollback()
        raise bss_http_error(e)
    expires_at = now + otp.OTP_TTL
    return _json(
        {
            "action_id": action_id,
            "kind": body.kind,
            **fields,
            "expires_at": expires_at,
            "otp": {"code": code, "to": masked, "expires_at": expires_at},
        }
    )


@router.post("/{action_id}/confirm", response_model=ActionResult)
def confirm(
    action_id: uuid.UUID,
    body: ActionConfirm,
    subscriber_id: uuid.UUID = Depends(get_current_subscriber),
    db: Session = Depends(get_db),
):
    kind = body.action.kind
    try:
        req, payload = _request(body.action)
        # verify commits a wrong-code attempt itself, so the lockout survives the 400.
        otp.verify(
            db,
            subscriber_id=subscriber_id,
            action_id=action_id,
            purpose=kind,
            payload=payload,
            code=otp.normalise_code(body.code),
        )
        kw = {"action_id": action_id, "actor": Actor.portal}
        if kind == "purchase":
            r = packages.execute_purchase(db, subscriber_id, req, **kw)
            out = {"main_balance": r.main_balance, "postpaid_due": r.postpaid_due}
        elif kind == "recharge":
            r = recharge.execute_recharge(db, subscriber_id, req, **kw)
            out = {"main_balance": r.main_balance, "postpaid_due": r.postpaid_due}
        else:
            r = rewards.execute_redeem(db, subscriber_id, req, **kw)
            out = {"reward_points": r.reward_points}
        db.commit()
    except BssError as e:
        db.rollback()
        raise bss_http_error(e)
    return _json(
        {
            "kind": kind,
            "ref": r.transaction_ref,
            "main_balance": None,
            "postpaid_due": None,
            "reward_points": None,
            **out,
        }
    )
