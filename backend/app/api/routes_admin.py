"""Admin portal reads: control center, subscribers, transactions, AI monitor."""

import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.bss_http import bss_http_error
from app.api.deps import get_current_admin, get_db
from app.api.schemas_admin import (
    AiMonitor,
    CaseList,
    CaseStats,
    CaseStatusIn,
    IncidentIn,
    NetworkOverview,
    Overview,
    SubscriberDetail,
    SubscriberList,
    TransactionList,
    TransactionStats,
)
from app.bss import audit, cases, monitor, network, notifications, ops
from app.bss.clock import utc_now
from app.bss.errors import BssError
from app.bss.network import IncidentAdminView
from app.bss.types import CaseView
from app.models.telco import Actor, CasePriority, CaseStatus, PlanType, SubscriberStatus, TxnStatus, TxnType

router = APIRouter(
    prefix="/api/admin", tags=["admin"], dependencies=[Depends(get_current_admin)]
)
_NO_STORE = {"Cache-Control": "no-store"}
_WINDOWS = {"24h": timedelta(hours=24), "7d": timedelta(days=7)}


def _dump(x: Any) -> Any:
    if isinstance(x, BaseModel):
        return {k: _dump(v) for k, v in x.__dict__.items()}
    if isinstance(x, dict):
        return {k: _dump(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_dump(i) for i in x]
    return x


def _json(payload: Any) -> JSONResponse:
    """JSON with Decimals as numbers (pydantic's JSON mode makes them strings)."""
    body = jsonable_encoder(_dump(payload), custom_encoder={Decimal: float})
    return JSONResponse(body, headers=_NO_STORE)


@router.get("/overview", response_model=Overview)
def overview(db: Session = Depends(get_db)):
    return _json(ops.overview(db))


@router.get("/subscribers", response_model=SubscriberList)
def subscribers(
    q: str | None = None,
    plan_type: PlanType | None = None,
    status: SubscriberStatus | None = None,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    items, total = ops.list_subscribers(
        db, q=q, plan_type=plan_type, status=status, limit=limit, offset=offset
    )
    return _json({"items": items, "total": total})


@router.get("/subscribers/{subscriber_id}", response_model=SubscriberDetail)
def subscriber_detail(subscriber_id: uuid.UUID, db: Session = Depends(get_db)):
    try:
        return _json(ops.subscriber_detail(db, subscriber_id))
    except BssError as e:
        raise bss_http_error(e)


@router.get("/transactions", response_model=TransactionList)
def transactions(
    status: TxnStatus | None = None,
    type: TxnType | None = None,
    q: str | None = None,
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    items, total = ops.list_transactions(
        db, status=status, type=type, q=q, days=days, limit=limit, offset=offset
    )
    return _json({"items": items, "total": total})


@router.get("/transactions/stats", response_model=TransactionStats)
def transaction_stats(db: Session = Depends(get_db)):
    return _json(ops.transaction_stats(db))


@router.get("/ai-monitor", response_model=AiMonitor)
def ai_monitor(window: Literal["24h", "7d"] = "24h", db: Session = Depends(get_db)):
    since = utc_now() - _WINDOWS[window]
    return _json(
        {
            "metrics": monitor.metrics(db, since=since),
            "review_queue": monitor.review_queue(db, since=since),
            "audit_trail": monitor.audit_trail(db),
        }
    )


@router.get("/cases", response_model=CaseList)
def case_list(
    status: CaseStatus | None = None,
    priority: CasePriority | None = None,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    items, total = ops.list_cases(db, status=status, priority=priority, limit=limit, offset=offset)
    return _json({"items": items, "total": total})


@router.get("/cases/stats", response_model=CaseStats)
def case_stats(db: Session = Depends(get_db)):
    return _json(ops.case_stats(db))


@router.patch("/cases/{ref}", response_model=CaseView)
def set_case_status(ref: str, body: CaseStatusIn, db: Session = Depends(get_db)):
    try:
        return _json(cases.set_case_status(db, ref, body.status))
    except BssError as e:
        raise bss_http_error(e)


@router.get("/network", response_model=NetworkOverview)
def network_overview(db: Session = Depends(get_db)):
    return _json(ops.network_overview(db))


@router.post("/network/incidents", response_model=IncidentAdminView, status_code=201)
def create_incident(body: IncidentIn, db: Session = Depends(get_db)):
    try:
        view = network.create_incident(db, **body.model_dump())
    except BssError as e:
        raise bss_http_error(e)
    return JSONResponse(jsonable_encoder(_dump(view)), status_code=201, headers=_NO_STORE)


@router.post("/network/incidents/{incident_id}/resolve", response_model=IncidentAdminView)
def resolve_incident(incident_id: uuid.UUID, db: Session = Depends(get_db)):
    try:
        return _json(network.resolve_incident(db, incident_id))
    except BssError as e:
        raise bss_http_error(e)


@router.post("/nudges/run")
def run_nudges(db: Session = Depends(get_db)):
    created = notifications.run_sweep(db)
    audit.record(
        db, actor=Actor.admin, action="nudges_run", subscriber_id=None, detail=dict(created)
    )
    db.commit()
    return _json({"created": created})
