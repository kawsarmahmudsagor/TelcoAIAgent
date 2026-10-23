"""Admin management of offers: validated create / update / delete."""

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.bss import audit
from app.bss.accounts import mask_msisdn
from app.bss.errors import InvalidRequest, OfferInUse, OfferNotFound
from app.models.telco import (
    Actor,
    Offer,
    OfferAudience,
    Package,
    Subscriber,
    Transaction,
)

_FIELDS = (
    "title", "description", "terms", "package_id", "points_cost", "cashback_percent",
    "cashback_cap", "min_recharge", "audience", "starts_on", "ends_on", "is_active",
)
_KIND_FIELDS = {
    "points": {"points_cost", "package_id"},
    "cashback": {"cashback_percent", "min_recharge", "cashback_cap"},
    "pack": {"package_id"},
}
_ALL_KIND_FIELDS = {"package_id", "points_cost", "cashback_percent", "cashback_cap", "min_recharge"}


def offer_kind(v: dict[str, Any]) -> str | None:
    """Derived kind from the offer's kind fields."""
    if v.get("points_cost") is not None:
        return "points"
    if v.get("cashback_percent") is not None:
        return "cashback"
    if v.get("package_id") is not None:
        return "pack"
    return None


def _validate(db: Session, v: dict[str, Any], subscriber_ids: list[uuid.UUID]) -> None:
    kind = offer_kind(v)
    if kind is None:
        raise InvalidRequest("Set the fields of exactly one offer kind")
    extra = {k for k in _ALL_KIND_FIELDS if v.get(k) is not None} - _KIND_FIELDS[kind]
    if extra:
        raise InvalidRequest(f"Fields mixed with a {kind} offer: {', '.join(sorted(extra))}")
    if kind == "points":
        if v["package_id"] is None or v["points_cost"] <= 0:
            raise InvalidRequest("A points offer needs a package and points_cost > 0")
    elif kind == "cashback":
        if not (Decimal(0) < v["cashback_percent"] <= Decimal(100)):
            raise InvalidRequest("cashback_percent must be above 0 and at most 100")
        if v["min_recharge"] is None:
            raise InvalidRequest("A cashback offer needs min_recharge")
    if v["package_id"] is not None and db.get(Package, v["package_id"]) is None:
        raise InvalidRequest("Unknown package")
    if v["starts_on"] and v["ends_on"] and v["ends_on"] < v["starts_on"]:
        raise InvalidRequest("ends_on must not be before starts_on")
    if v["audience"] == OfferAudience.specific and not subscriber_ids:
        raise InvalidRequest("A specific audience needs at least one subscriber")


def _subscribers(db: Session, ids: list[uuid.UUID]) -> list[Subscriber]:
    wanted = set(ids)
    rows = list(db.scalars(select(Subscriber).where(Subscriber.id.in_(wanted))))
    if len(rows) != len(wanted):
        raise InvalidRequest("Unknown subscriber in subscriber_ids")
    return rows


def _redemptions(db: Session, offer_id: uuid.UUID) -> int:
    return db.scalar(
        select(func.count()).select_from(Transaction).where(Transaction.offer_id == offer_id)
    )


def _view(db: Session, o: Offer) -> dict[str, Any]:
    pkg = db.get(Package, o.package_id) if o.package_id else None
    subs = o.subscribers if o.audience == OfferAudience.specific else []
    return {
        "id": o.id,
        "title": o.title,
        "description": o.description,
        "terms": o.terms,
        "kind": offer_kind({k: getattr(o, k) for k in _ALL_KIND_FIELDS}),
        "package_id": o.package_id,
        "package_name": pkg.name if pkg else None,
        "points_cost": o.points_cost,
        "cashback_percent": o.cashback_percent,
        "cashback_cap": o.cashback_cap,
        "min_recharge": o.min_recharge,
        "audience": o.audience,
        "subscriber_ids": [s.id for s in subs],
        "subscribers": [
            {"id": s.id, "full_name": s.full_name, "msisdn_masked": mask_msisdn(s.msisdn)}
            for s in subs
        ],
        "starts_on": o.starts_on,
        "ends_on": o.ends_on,
        "is_active": o.is_active,
        "redemptions": _redemptions(db, o.id),
    }


def list_offers(db: Session) -> list[dict[str, Any]]:
    rows = db.scalars(select(Offer).order_by(Offer.created_at.desc(), Offer.title.asc()))
    return [_view(db, o) for o in rows]


def _get(db: Session, offer_id: uuid.UUID) -> Offer:
    o = db.get(Offer, offer_id)
    if o is None:
        raise OfferNotFound()
    return o


def _apply(db: Session, o: Offer, values: dict[str, Any], ids: list[uuid.UUID]) -> None:
    _validate(db, values, ids)
    subs = _subscribers(db, ids) if values["audience"] == OfferAudience.specific else []
    for k in _FIELDS:
        setattr(o, k, values[k])
    o.subscribers = subs


def create_offer(
    db: Session, fields: dict[str, Any], subscriber_ids: list[uuid.UUID]
) -> dict[str, Any]:
    values = {k: fields.get(k) for k in _FIELDS}
    values["audience"] = values["audience"] or OfferAudience.all
    values["is_active"] = True if values["is_active"] is None else values["is_active"]
    o = Offer()
    _apply(db, o, values, subscriber_ids)
    db.add(o)
    db.flush()
    audit.record(
        db, actor=Actor.admin, action="offer_create", subscriber_id=None,
        detail={"offer_id": str(o.id), "title": o.title},
    )
    db.commit()
    return _view(db, o)


def update_offer(
    db: Session,
    offer_id: uuid.UUID,
    changes: dict[str, Any],
    subscriber_ids: list[uuid.UUID] | None,
) -> dict[str, Any]:
    """`changes` holds only the fields the caller sent (an explicit None clears a field)."""
    o = _get(db, offer_id)
    values = {k: getattr(o, k) for k in _FIELDS}
    values.update(changes)
    if values["title"] is None or values["audience"] is None or values["is_active"] is None:
        raise InvalidRequest("title, audience and is_active cannot be null")
    ids = [s.id for s in o.subscribers] if subscriber_ids is None else subscriber_ids
    _apply(db, o, values, ids)
    audit.record(
        db, actor=Actor.admin, action="offer_update", subscriber_id=None,
        detail={"offer_id": str(o.id), "fields": sorted(changes)},
    )
    db.commit()
    return _view(db, o)


def delete_offer(db: Session, offer_id: uuid.UUID) -> None:
    o = _get(db, offer_id)
    if _redemptions(db, o.id):
        raise OfferInUse()
    audit.record(
        db, actor=Actor.admin, action="offer_delete", subscriber_id=None,
        detail={"offer_id": str(o.id), "title": o.title},
    )
    db.delete(o)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise OfferInUse()
