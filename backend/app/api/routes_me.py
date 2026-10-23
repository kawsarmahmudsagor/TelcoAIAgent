"""Customer portal: the signed-in subscriber's own data."""

import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.bss_http import bss_http_error
from app.api.deps import get_current_subscriber, get_db
from app.api.schemas_me import NotificationList, PortalCaseCreate, PortalMe, ReadAllResult
from app.bss import accounts, cases, network, notifications, packages, rewards, transactions
from app.bss.errors import BssError
from app.bss.types import (
    AccountSummary,
    CaseView,
    IncidentView,
    NotificationView,
    OffersAndPoints,
    PackageView,
    Recommendation,
    TransactionView,
    UsageBreakdown,
)
from app.models.telco import (
    CaseSource,
    PackageKind,
    Subscriber,
    TxnStatus,
    TxnType,
    UsageKind,
)

router = APIRouter(prefix="/api/me", tags=["portal"])
_NO_STORE = {"Cache-Control": "no-store"}
_CASE_LIMIT = 20


def _json(payload: Any, status_code: int = 200) -> JSONResponse:
    """JSON with Decimals as numbers (pydantic's JSON mode makes them strings)."""

    def dump(x: Any) -> Any:
        if isinstance(x, BaseModel):
            return x.model_dump()
        if isinstance(x, list):
            return [dump(i) for i in x]
        return x

    body = jsonable_encoder(dump(payload), custom_encoder={Decimal: float})
    return JSONResponse(body, status_code=status_code, headers=_NO_STORE)


def portal_me(sub: Subscriber) -> PortalMe:
    return PortalMe(
        subscriber_id=sub.id,
        full_name=sub.full_name,
        first_name=sub.full_name.split()[0],
        msisdn=sub.msisdn,
        masked_msisdn=accounts.mask_msisdn(sub.msisdn),
        plan_type=sub.plan_type,
        district=sub.district,
    )


@router.get("", response_model=PortalMe)
def me(
    response: Response,
    subscriber_id: uuid.UUID = Depends(get_current_subscriber),
    db: Session = Depends(get_db),
) -> PortalMe:
    response.headers.update(_NO_STORE)
    return portal_me(db.get(Subscriber, subscriber_id))


@router.get("/summary", response_model=AccountSummary)
def summary(
    subscriber_id: uuid.UUID = Depends(get_current_subscriber), db: Session = Depends(get_db)
):
    try:
        return _json(accounts.get_account_summary(db, subscriber_id))
    except BssError as e:
        raise bss_http_error(e)


@router.get("/usage", response_model=UsageBreakdown)
def usage(
    period_days: int = Query(30, ge=1, le=90),
    kind: UsageKind | None = None,
    subscriber_id: uuid.UUID = Depends(get_current_subscriber),
    db: Session = Depends(get_db),
):
    try:
        return _json(
            accounts.get_usage_breakdown(db, subscriber_id, period_days=period_days, kind=kind)
        )
    except BssError as e:
        raise bss_http_error(e)


@router.get("/transactions", response_model=list[TransactionView])
def list_transactions(
    type: TxnType | None = None,
    status: TxnStatus | None = None,
    days: int = Query(30, ge=1, le=90),
    limit: int = Query(20, ge=1, le=50),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber),
    db: Session = Depends(get_db),
):
    try:
        return _json(
            transactions.lookup(
                db, subscriber_id, type=type, status=status, days=days, limit=limit
            )
        )
    except BssError as e:
        raise bss_http_error(e)


@router.get("/packages", response_model=list[PackageView])
def list_packages(
    kind: PackageKind | None = None,
    subscriber_id: uuid.UUID = Depends(get_current_subscriber),
    db: Session = Depends(get_db),
):
    return _json(packages.search(db, kind=kind))


@router.get("/recommendations", response_model=list[Recommendation])
def recommendations(
    subscriber_id: uuid.UUID = Depends(get_current_subscriber), db: Session = Depends(get_db)
):
    try:
        return _json(packages.recommend(db, subscriber_id))
    except BssError as e:
        raise bss_http_error(e)


@router.get("/offers", response_model=OffersAndPoints)
def offers(
    subscriber_id: uuid.UUID = Depends(get_current_subscriber), db: Session = Depends(get_db)
):
    try:
        return _json(rewards.get_offers_and_points(db, subscriber_id))
    except BssError as e:
        raise bss_http_error(e)


@router.get("/cases", response_model=list[CaseView])
def list_cases(
    subscriber_id: uuid.UUID = Depends(get_current_subscriber), db: Session = Depends(get_db)
):
    rows = cases.get_case_status(db, subscriber_id, limit=_CASE_LIMIT)
    # bss lists open cases first; the portal shows newest first.
    return _json(sorted(rows, key=lambda c: c.created_at, reverse=True))


@router.post("/cases", response_model=CaseView, status_code=201)
def create_case(
    body: PortalCaseCreate,
    subscriber_id: uuid.UUID = Depends(get_current_subscriber),
    db: Session = Depends(get_db),
):
    try:
        case = cases.create_case(
            db,
            subscriber_id,
            category=body.category,
            description=body.description,
            priority=body.priority,
            source=CaseSource.portal,
            action_id=body.request_id,
        )
        db.commit()
    except BssError as e:
        db.rollback()
        raise bss_http_error(e)
    return _json(case, status_code=201)


@router.get("/network", response_model=list[IncidentView])
def network_status(
    subscriber_id: uuid.UUID = Depends(get_current_subscriber), db: Session = Depends(get_db)
):
    sub = db.get(Subscriber, subscriber_id)
    return _json(network.check_network_status(db, sub.district))


@router.get("/notifications", response_model=NotificationList)
def list_notifications(
    subscriber_id: uuid.UUID = Depends(get_current_subscriber), db: Session = Depends(get_db)
):
    unread, items = notifications.list_for(db, subscriber_id)
    return _json({"unread": unread, "items": items})


@router.post("/notifications/read-all", response_model=ReadAllResult)
def read_all_notifications(
    subscriber_id: uuid.UUID = Depends(get_current_subscriber), db: Session = Depends(get_db)
):
    return _json({"updated": notifications.mark_all_read(db, subscriber_id)})


@router.post("/notifications/{notification_id}/read", response_model=NotificationView)
def read_notification(
    notification_id: uuid.UUID,
    subscriber_id: uuid.UUID = Depends(get_current_subscriber),
    db: Session = Depends(get_db),
):
    try:
        return _json(notifications.mark_read(db, subscriber_id, notification_id))
    except BssError as e:
        db.rollback()
        raise bss_http_error(e)
