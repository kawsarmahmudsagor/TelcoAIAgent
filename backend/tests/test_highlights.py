import asyncio
import itertools
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.agent import highlights
from app.agent.tools import account
from app.agent.userdata import Channel, SessionUserdata
from app.bss import accounts
from app.bss.clock import local_day_start, local_tz
from app.models.telco import (
    PackageKind,
    PlanType,
    Transaction,
    TxnChannel,
    TxnStatus,
    TxnType,
    UsageKind,
)

_refs = itertools.count(random.randint(0, 9000))


def _ud(sub) -> SessionUserdata:
    return SessionUserdata(channel=Channel.inbound_chat, room=None, subscriber_id=sub.id)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today():
    return _now().astimezone(local_tz()).date()


def _bought(world, sub, pkg, days_ago: int = 1) -> None:
    world.db.add(
        Transaction(
            ref=f"TXN-8{next(_refs):04d}",
            subscriber_id=sub.id,
            type=TxnType.purchase,
            channel=TxnChannel.balance,
            amount=pkg.price,
            package_id=pkg.id,
            status=TxnStatus.success,
            created_at=_now() - timedelta(days=days_ago),
        )
    )
    world.db.commit()


def _highlights(world, sub) -> list[str]:
    now = _now()
    return highlights.account_highlights(
        world.db, accounts.get_account_summary(world.db, sub.id, now=now), now
    )


def test_relative_day():
    today = _today()
    noon = lambda d: local_day_start(d) + timedelta(hours=12)  # noqa: E731
    assert highlights.relative_day(noon(today), today) == "today"
    assert highlights.relative_day(noon(today + timedelta(days=1)), today) == "tomorrow"
    assert highlights.relative_day(noon(today + timedelta(days=2)), today) is None


def test_a_quiet_account_has_nothing_to_mention(bss_world):
    sub = bss_world.subscriber(main_balance=Decimal("500"), reward_points=0)
    pkg = bss_world.package(kind=PackageKind.data, data_mb=10240)
    bss_world.subscription(sub, pkg, expires_in_days=10)
    assert _highlights(bss_world, sub) == []
    assert highlights.block([]) == ""


def test_pack_expiring_today_without_auto_renew(bss_world):
    sub = bss_world.subscriber(reward_points=0)
    bonus = bss_world.package(name="PYTEST Bonus 1GB", kind=PackageKind.data, data_mb=1024)
    renewing = bss_world.package(name="PYTEST Renewing", kind=PackageKind.data, data_mb=1024)
    end_of_today = local_day_start(_today() + timedelta(days=1)) - timedelta(seconds=30)
    if end_of_today <= _now():  # the last half minute of the day: nothing expires "today"
        return
    bss_world.subscription(sub, bonus, expires_at=end_of_today)
    bss_world.subscription(sub, renewing, expires_at=end_of_today, auto_renew=True)
    found = _highlights(bss_world, sub)
    assert found == ["Their PYTEST Bonus 1GB expires today and doesn't auto-renew."]

    out = asyncio.run(account.run_get_account_summary(_ud(sub)))
    assert "expires today (" in out
    assert out.endswith(highlights.block(found))


def test_low_data(bss_world):
    sub = bss_world.subscriber(reward_points=0)
    pkg = bss_world.package(kind=PackageKind.data, data_mb=1024)
    bss_world.subscription(sub, pkg, data_left_mb=120, expires_in_days=10)
    assert _highlights(bss_world, sub) == ["Only 120 MB data left across their packages."]


def test_balance_below_last_bought_pack(bss_world):
    sub = bss_world.subscriber(main_balance=Decimal("50"), reward_points=0)
    old = bss_world.package(name="PYTEST Old", price=Decimal("20"))
    last = bss_world.package(name="PYTEST Smart", price=Decimal("399"))
    _bought(bss_world, sub, old, days_ago=40)
    _bought(bss_world, sub, last, days_ago=3)
    [found] = _highlights(bss_world, sub)
    assert "PYTEST Smart (399 taka)" in found and "recharge" in found

    rich = bss_world.subscriber(main_balance=Decimal("500"), reward_points=0)
    _bought(bss_world, rich, last)
    postpaid = bss_world.subscriber(plan_type=PlanType.postpaid, reward_points=0)
    _bought(bss_world, postpaid, last)
    assert _highlights(bss_world, rich) == [] and _highlights(bss_world, postpaid) == []


def test_redeemable_points(bss_world):
    sub = bss_world.subscriber(reward_points=5000)
    bss_world.offer(title="PYTEST Offer Cheap", points_cost=1)
    bss_world.offer(title="PYTEST Offer Pricey", points_cost=999_999)
    found = [h for h in _highlights(bss_world, sub) if "points can be redeemed" in h]
    assert found and "PYTEST Offer Cheap for 1 points" in found[0]
    assert "PYTEST Offer Pricey" not in found[0]

    poor = bss_world.subscriber(reward_points=0)
    assert _highlights(bss_world, poor) == []


def test_data_well_above_the_usual_week(bss_world):
    sub = bss_world.subscriber()
    now = _now()
    for week in (1, 2, 3):  # 300 MB in each of the three weeks before this one
        bss_world.usage(sub, UsageKind.data, 300, at=now - timedelta(days=7 * week + 2))
    bss_world.usage(sub, UsageKind.data, 1200, at=now - timedelta(hours=2))
    [found] = highlights.usage_highlights(bss_world.db, sub.id, now)
    assert "1.2 GB" in found or "1200 MB" in found
    assert "300 MB a week" in found

    out = asyncio.run(account.run_get_usage_breakdown(_ud(sub), 7))
    assert "well above their usual" in out
    voice_only = asyncio.run(account.run_get_usage_breakdown(_ud(sub), 7, "voice"))
    assert "well above" not in voice_only


def test_small_jumps_and_no_history_are_not_news(bss_world):
    sub = bss_world.subscriber()
    now = _now()
    for week in (1, 2, 3):
        bss_world.usage(sub, UsageKind.data, 50, at=now - timedelta(days=7 * week + 2))
    bss_world.usage(sub, UsageKind.data, 200, at=now - timedelta(hours=2))  # 4x, but +150 MB
    assert highlights.usage_highlights(bss_world.db, sub.id, now) == []

    new = bss_world.subscriber()
    bss_world.usage(new, UsageKind.data, 5000, at=now - timedelta(hours=2))
    assert highlights.usage_highlights(bss_world.db, new.id, now) == []


def test_out_of_data_only_matters_to_data_users(bss_world):
    sub = bss_world.subscriber(reward_points=0)
    sms = bss_world.package(kind=PackageKind.sms, sms=100)
    bss_world.subscription(sub, sms, expires_in_days=10)
    assert _highlights(bss_world, sub) == []
    bss_world.usage(sub, UsageKind.data, 668, at=_now() - timedelta(hours=3))
    [found] = _highlights(bss_world, sub)
    assert "no data left" in found and "668 MB" in found


def test_snapshot_carries_the_highlights(bss_world):
    from app.agent.snapshot import load_snapshot

    sub = bss_world.subscriber(reward_points=0)
    pkg = bss_world.package(kind=PackageKind.data, data_mb=1024)
    bss_world.subscription(sub, pkg, data_left_mb=120, expires_in_days=10)
    text = load_snapshot(sub.id)
    assert text.endswith(highlights.block(["Only 120 MB data left across their packages."]))


def test_points_note_says_whether_points_buy_anything(bss_world):
    bss_world.offer(title="PYTEST Offer Points", points_cost=1)
    poor = bss_world.subscriber(reward_points=0)
    rich = bss_world.subscriber(reward_points=10**8)
    now = _now()
    assert "not enough for any reward yet" in highlights.points_note(bss_world.db, poor.id, 0, now)
    assert "enough for" in highlights.points_note(bss_world.db, rich.id, 10**8, now)
    out = asyncio.run(account.run_get_account_summary(_ud(poor)))
    assert "Reward points: 0 (not enough for any reward yet" in out
