from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.bss import otp, rewards
from app.bss.clock import local_tz
from app.bss.errors import InsufficientPoints, OfferNotEligible
from app.models.telco import (
    Actor,
    AuditEvent,
    OfferAudience,
    PlanType,
    Subscriber,
    Subscription,
    Transaction,
    TxnChannel,
    TxnType,
)


def _confirm(db, sub, offer):
    aid = uuid4()
    payload = {"offer_id": str(offer.id)}
    code = otp.issue(db, subscriber_id=sub.id, action_id=aid, purpose="redeem", payload=payload)
    otp.verify(
        db, subscriber_id=sub.id, action_id=aid, purpose="redeem", payload=payload, code=code
    )
    return aid


def _redeem(db, sub, offer, aid=None):
    return rewards.execute_redeem(
        db, sub.id, offer.id, action_id=aid or _confirm(db, sub, offer), actor=Actor.agent
    )


def _points(db, sub):
    db.expire_all()
    return db.get(Subscriber, sub.id).reward_points


def test_offers_filtered_by_audience_and_dates(bss_world, db):
    s = bss_world.subscriber(plan_type=PlanType.prepaid, reward_points=500)
    today = datetime.now(timezone.utc).astimezone(local_tz()).date()
    ok_all = bss_world.offer(title="PYTEST all")
    ok_pre = bss_world.offer(title="PYTEST prepaid", audience=OfferAudience.prepaid)
    post = bss_world.offer(title="PYTEST postpaid", audience=OfferAudience.postpaid)
    old = bss_world.offer(title="PYTEST old", ends_on=today - timedelta(days=1))
    future = bss_world.offer(title="PYTEST future", starts_on=today + timedelta(days=1))
    off = bss_world.offer(title="PYTEST inactive", is_active=False)
    last_day = bss_world.offer(title="PYTEST lastday", ends_on=today)
    res = rewards.get_offers_and_points(db, s.id)
    assert res.reward_points == 500
    ids = {o.id for o in res.offers}
    assert {ok_all.id, ok_pre.id, last_day.id} <= ids
    assert not ids & {post.id, old.id, future.id, off.id}


def test_redeem_exact_points_succeeds_and_grants_package(bss_world, db):
    s = bss_world.subscriber(reward_points=100)
    pkg = bss_world.package(data_mb=1024, validity_days=7)
    o = bss_world.offer(points_cost=100, package_id=pkg.id)
    q = rewards.preview_redeem(db, s.id, o.id)
    assert q.points_after == 0 and q.offer.package.code == pkg.code
    r = _redeem(db, s, o)
    assert r.reward_points == 0 and r.offer_title == o.title and r.expires_at is not None
    assert _points(db, s) == 0
    subs = db.scalars(select(Subscription).where(Subscription.subscriber_id == s.id)).all()
    assert len(subs) == 1 and subs[0].data_left_mb == 1024
    t = db.scalar(select(Transaction).where(Transaction.ref == r.transaction_ref))
    assert (t.type, t.channel, t.amount, t.offer_id) == (
        TxnType.redeem,
        TxnChannel.points,
        0,
        o.id,
    )


def test_redeem_insufficient_points(bss_world, db):
    s = bss_world.subscriber(reward_points=99)
    o = bss_world.offer(points_cost=100)
    with pytest.raises(InsufficientPoints):
        rewards.preview_redeem(db, s.id, o.id)
    with pytest.raises(InsufficientPoints):
        _redeem(db, s, o)
    assert _points(db, s) == 99


def test_redeem_not_eligible(bss_world, db):
    s = bss_world.subscriber(reward_points=500)
    cashback_only = bss_world.offer(cashback_percent=5)
    wrong = bss_world.offer(points_cost=10, audience=OfferAudience.postpaid)
    for o in (cashback_only, wrong):
        with pytest.raises(OfferNotEligible):
            rewards.preview_redeem(db, s.id, o.id)
    with pytest.raises(OfferNotEligible):
        rewards.preview_redeem(db, s.id, uuid4())


def test_redeem_requires_otp(bss_world, db):
    s = bss_world.subscriber(reward_points=100)
    o = bss_world.offer(points_cost=50)
    with pytest.raises(Exception) as e:
        rewards.execute_redeem(db, s.id, o.id, action_id=uuid4(), actor=Actor.agent)
    assert e.value.code in {"no_pending_action", "otp_invalid"}
    assert _points(db, s) == 100


def test_redeem_same_action_twice_is_noop(bss_world, db):
    s = bss_world.subscriber(reward_points=100)
    pkg = bss_world.package()
    o = bss_world.offer(points_cost=40, package_id=pkg.id)
    aid = _confirm(db, s, o)
    first = _redeem(db, s, o, aid)
    second = _redeem(db, s, o, aid)
    assert second.transaction_ref == first.transaction_ref
    assert second.reward_points == 60 == _points(db, s)
    assert second.expires_at == first.expires_at
    assert db.scalar(
        select(func.count()).select_from(Subscription).where(Subscription.subscriber_id == s.id)
    ) == 1
    assert db.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(AuditEvent.action_id == aid, AuditEvent.action == "redeem")
    ) == 1
