import asyncio
import json
import itertools
import random
from decimal import Decimal
from uuid import uuid4

import pytest
from livekit.agents.llm import ToolError

from app.agent.tools import account, network, packages, registry, rewards, support, transactions
from app.agent.tools._common import ERROR_TEXT, NOT_LOGGED_IN
from app.agent.userdata import Channel, SessionUserdata
from app.models.telco import (
    PackageKind,
    PlanType,
    Transaction,
    TxnChannel,
    TxnStatus,
    TxnType,
)

_refs = itertools.count(random.randint(0, 9000))


def _ud(sub=None, **kw) -> SessionUserdata:
    return SessionUserdata(
        channel=Channel.inbound_chat,
        room=None,
        subscriber_id=sub.id if sub is not None else kw.pop("subscriber_id", None),
        **kw,
    )


def _txn(world, sub, **o):
    row = Transaction(
        ref=f"TXN-9{next(_refs):04d}",
        subscriber_id=sub.id,
        type=TxnType.recharge,
        channel=TxnChannel.bkash,
        amount=Decimal("100"),
        status=TxnStatus.success,
        **o,
    )
    world.db.add(row)
    world.db.commit()
    return row


def test_account_summary_text_has_balance_and_pack(bss_world):
    sub = bss_world.subscriber(main_balance=Decimal("486.50"))
    pkg = bss_world.package(name="PYTEST Net 15", kind=PackageKind.data, data_mb=15360)
    bss_world.subscription(sub, pkg)
    out = asyncio.run(account.run_get_account_summary(_ud(sub)))
    assert "486.50 taka" in out and "15 GB" in out
    assert sub.msisdn not in out and sub.msisdn[-4:] in out


def test_postpaid_summary_shows_bill_due(bss_world):
    sub = bss_world.subscriber(plan_type=PlanType.postpaid, postpaid_due=Decimal("750"))
    out = asyncio.run(account.run_get_account_summary(_ud(sub)))
    assert "Bill due: 750 taka" in out and "Main balance" not in out


def test_usage_and_deductions_text(bss_world):
    from app.models.telco import UsageKind

    sub = bss_world.subscriber()
    bss_world.usage(sub, UsageKind.data, 2048, charge=30)
    out = asyncio.run(account.run_get_usage_breakdown(_ud(sub), 7, "data"))
    assert "2 GB" in out and "30 taka" in out
    out = asyncio.run(account.run_explain_deductions(_ud(sub), 7))
    assert "30 taka" in out


def test_usage_inside_a_package_says_no_charge(bss_world):
    from app.models.telco import UsageKind

    sub = bss_world.subscriber()
    bss_world.usage(sub, UsageKind.voice, 120, charge=0)
    out = asyncio.run(account.run_get_usage_breakdown(_ud(sub), 7))
    assert "voice: 120" in out and "charged" not in out


def test_search_packages_filters_and_caps_detail(bss_world):
    for i in range(5):
        bss_world.package(
            name=f"PYTEST Data {i}", kind=PackageKind.data, data_mb=1024, price=Decimal(50 + i),
            validity_days=17,
        )
    bss_world.package(name="PYTEST Dead", kind=PackageKind.data, data_mb=1024, is_active=False, validity_days=17)
    bss_world.package(name="PYTEST Voice", kind=PackageKind.voice, minutes=100, validity_days=17)
    out = asyncio.run(
        packages.run_search_packages(_ud(), kind="data", max_price=60, validity_days=17)
    )
    # All five reach the model, so "any others?" has an answer (run_28); it
    # reads out three at a time.
    assert out.count("- PYTEST Data") == 5
    assert "Name 3 at a time" in out
    assert "more not listed" not in out
    assert "PYTEST Dead" not in out and "PYTEST Voice" not in out


def test_search_packages_lists_ten_and_counts_the_rest(bss_world):
    for i in range(12):
        bss_world.package(
            name=f"PYTEST Bulk {i}", kind=PackageKind.data, data_mb=1024, price=Decimal(50 + i),
            validity_days=19,
        )
    out = asyncio.run(packages.run_search_packages(_ud(), kind="data", validity_days=19))
    assert out.count("- PYTEST Bulk") == 10
    assert "2 more not listed" in out


def _capture(monkeypatch) -> list[tuple[str, dict]]:
    sent: list[tuple[str, dict]] = []

    async def fake(userdata, topic, payload):
        sent.append((topic, json.loads(payload)))

    monkeypatch.setattr(packages.cards, "send_card", fake)
    return sent


def test_search_packages_publishes_cards(bss_world, monkeypatch):
    sent = _capture(monkeypatch)
    bss_world.package(name="PYTEST Card", kind=PackageKind.data, data_mb=2048, price=Decimal("49"),
                      validity_days=13)
    asyncio.run(packages.run_search_packages(_ud(), validity_days=13))
    (topic, payload), = sent
    assert topic == "telco.packages" and payload["title"] == "Packages"
    card = payload["packages"][0]
    assert card["name"] == "PYTEST Card" and card["kind"] == "data"
    assert isinstance(card["price"], float) and card["price"] == 49.0
    assert set(card) == {"code", "name", "kind", "data_mb", "minutes", "sms", "validity_days", "price", "tag"}


def test_empty_search_publishes_nothing(bss_world, monkeypatch):
    sent = _capture(monkeypatch)
    asyncio.run(packages.run_search_packages(_ud(), validity_days=9999))
    assert sent == []


def test_recommend_publishes_cards(bss_world, monkeypatch):
    from app.models.telco import UsageKind

    sent = _capture(monkeypatch)
    sub = bss_world.subscriber()
    bss_world.package(name="PYTEST Fit", kind=PackageKind.data, data_mb=5120)
    bss_world.usage(sub, UsageKind.data, 1000)
    asyncio.run(packages.run_recommend_packages(_ud(sub)))
    assert sent[0][0] == "telco.packages" and sent[0][1]["title"] == "Recommended for you"
    assert 1 <= len(sent[0][1]["packages"]) <= 6


def test_search_packages_bad_kind_maps_invalid_request():
    with pytest.raises(ToolError, match="rephrase"):
        asyncio.run(packages.run_search_packages(_ud(), kind="gold"))


def test_recommend_packages_lists_fit(bss_world):
    from app.models.telco import UsageKind

    sub = bss_world.subscriber()
    bss_world.package(name="PYTEST Fit", kind=PackageKind.data, data_mb=5120)
    bss_world.usage(sub, UsageKind.data, 1000)
    out = asyncio.run(packages.run_recommend_packages(_ud(sub)))
    assert "PYTEST Fit" in out


def test_offers_are_numbered_and_remembered(bss_world):
    sub = bss_world.subscriber()
    a = bss_world.offer(title="PYTEST Offer A", points_cost=100)
    b = bss_world.offer(title="PYTEST Offer B", cashback_percent=Decimal("5"))
    ud = _ud(sub)
    out = asyncio.run(rewards.run_get_offers_and_points(ud))
    assert "#1" in out and "#2" in out
    assert {a.id, b.id} <= set(ud.offer_ids)
    assert ud.offer_ids.index(a.id) < ud.offer_ids.index(b.id)
    assert out.index("PYTEST Offer A") < out.index("PYTEST Offer B")


def test_check_network_defaults_to_subscriber_district(bss_world):
    sub = bss_world.subscriber(district="Sylhet")
    bss_world.incident(district="Sylhet", area="PYTEST Zindabazar")
    bss_world.incident(district="Dhaka", area="PYTEST Gulshan")
    out = asyncio.run(network.run_check_network_status(_ud(sub)))
    assert "PYTEST Zindabazar" in out and "PYTEST Gulshan" not in out
    out = asyncio.run(network.run_check_network_status(_ud(), "Dhaka"))
    assert "PYTEST Gulshan" in out


def test_check_network_guest_without_district_asks():
    assert "which district" in asyncio.run(network.run_check_network_status(_ud()))


def test_get_case_status_unknown_ref_maps_error(bss_world):
    sub = bss_world.subscriber()
    with pytest.raises(ToolError) as e:
        asyncio.run(support.run_get_case_status(_ud(sub), "TC-1"))
    assert str(e.value) == ERROR_TEXT["case_not_found"]


def test_no_cases_text(bss_world):
    sub = bss_world.subscriber()
    assert "no support cases" in asyncio.run(support.run_get_case_status(_ud(sub)))


def test_bad_period_maps_invalid_request(bss_world):
    sub = bss_world.subscriber()
    with pytest.raises(ToolError) as e:
        asyncio.run(account.run_get_usage_breakdown(_ud(sub), period_days=91))
    assert str(e.value) == ERROR_TEXT["invalid_request"]


def test_usage_today_and_any_period(bss_world):
    from app.models.telco import UsageKind

    sub = bss_world.subscriber()
    bss_world.usage(sub, UsageKind.data, 1024)
    out = asyncio.run(account.run_get_usage_breakdown(_ud(sub), 1, "data"))
    assert out.startswith("Usage today:") and "Heaviest data day" not in out
    out = asyncio.run(account.run_get_usage_breakdown(_ud(sub), 3, "data"))
    assert out.startswith("Usage in the last 3 days:")


def test_bad_enum_maps_invalid_request(bss_world):
    sub = bss_world.subscriber()
    with pytest.raises(ToolError) as e:
        asyncio.run(transactions.run_lookup_transactions(_ud(sub), type="gift"))
    assert str(e.value) == ERROR_TEXT["invalid_request"]


def _every_account_tool(ud):
    return [
        account.run_get_account_summary(ud),
        account.run_get_usage_breakdown(ud),
        account.run_explain_deductions(ud),
        packages.run_recommend_packages(ud),
        transactions.run_lookup_transactions(ud),
        rewards.run_get_offers_and_points(ud),
        support.run_get_case_status(ud),
    ]


def test_tools_without_subscriber_say_log_in(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("DB touched")

    monkeypatch.setattr("app.agent.tools._common.SessionLocal", boom)

    async def go():
        for coro in _every_account_tool(_ud()):
            assert await coro == NOT_LOGGED_IN

    asyncio.run(go())


def test_unknown_subscriber_says_log_in(db):
    async def go():
        ud = _ud(subscriber_id=uuid4())
        for coro in _every_account_tool(ud):
            assert await coro == NOT_LOGGED_IN
        assert await network.run_check_network_status(ud) == NOT_LOGGED_IN

    asyncio.run(go())


def test_reads_scoped_to_session_subscriber(bss_world):
    a, b = bss_world.subscriber(), bss_world.subscriber()
    ta, tb = _txn(bss_world, a), _txn(bss_world, b)
    out = asyncio.run(transactions.run_lookup_transactions(_ud(a)))
    assert ta.ref in out and tb.ref not in out
    out = asyncio.run(transactions.run_lookup_transactions(_ud(a), ref=tb.ref))
    assert tb.ref not in out


def test_transactions_list_ten_with_the_real_count(bss_world):
    # "আগের রিচার্জগুলো?" needs them all, and 12 is not "10 transactions".
    sub = bss_world.subscriber()
    for _ in range(12):
        _txn(bss_world, sub)
    out = asyncio.run(transactions.run_lookup_transactions(_ud(sub)))
    assert out.startswith("12 transactions")
    assert out.count("- TXN-") == 10
    assert "Name 3 at a time" in out and "2 more not listed" in out


@pytest.mark.parametrize("said", ["txn {n}", "TXN{n}", " TXN-{n} ", "{n}"])
def test_transaction_ref_however_said(bss_world, said):
    sub = bss_world.subscriber()
    row = _txn(bss_world, sub)
    digits = row.ref.removeprefix("TXN-")
    out = asyncio.run(transactions.run_lookup_transactions(_ud(sub), ref=said.format(n=digits)))
    assert out.startswith("1 transactions") and row.ref in out


def test_deductions_list_them_all(bss_world):
    from app.models.telco import UsageKind

    sub = bss_world.subscriber()
    for i in range(5):
        bss_world.usage(sub, UsageKind.voice, 1, charge=10 + i)
    out = asyncio.run(account.run_explain_deductions(_ud(sub), 7))
    assert out.startswith("5 deductions") and out.count("\n- ") == 5
    assert "more not listed" not in out


def test_case_status_lists_them_all_with_the_real_count(bss_world, db):
    from app.bss import cases
    from app.models.telco import CaseSource

    sub = bss_world.subscriber()
    for i in range(7):
        cases.create_case(
            db, sub.id, category=f"case_{i}", description="PYTEST", source=CaseSource.agent,
            action_id=uuid4(),
        )
    out = asyncio.run(support.run_get_case_status(_ud(sub)))
    assert out.startswith("7 support case(s)") and out.count("- TC-") == 7


@pytest.mark.parametrize(
    ("place", "district"),
    [("সিলেট", "PYTEST Zindabazar"), ("Sylhet", "PYTEST Zindabazar"), ("Tongi", "PYTEST Tongi")],
)
def test_network_by_area_or_in_bangla(bss_world, place, district):
    # run_28 audit: "সিলেট" and "Tongi" read as all clear.
    bss_world.incident(district="Sylhet", area="PYTEST Zindabazar")
    bss_world.incident(district="Gazipur", area="PYTEST Gazipur Sadar")
    bss_world.incident(district="Gazipur", area="PYTEST Tongi")
    out = asyncio.run(network.run_check_network_status(_ud(), place))
    assert district in out


def test_network_area_comes_first_and_says_its_district(bss_world):
    bss_world.incident(district="Gazipur", area="PYTEST Gazipur Sadar")
    bss_world.incident(district="Gazipur", area="PYTEST Tongi")
    out = asyncio.run(network.run_check_network_status(_ud(), "Tongi"))
    assert "(Tongi is in Gazipur)" in out
    assert out.index("PYTEST Tongi") < out.index("PYTEST Gazipur Sadar")


def test_network_unknown_place_asks_instead_of_all_clear():
    out = asyncio.run(network.run_check_network_status(_ud(), "Atlantis"))
    assert "Ask which district" in out and "No network problems" not in out


def test_transaction_text_no_repeated_type(bss_world):
    sub = bss_world.subscriber()
    row = _txn(bss_world, sub)
    out = asyncio.run(transactions.run_lookup_transactions(_ud(sub)))
    assert f"{row.ref}: recharge of 100 taka" in out and "recharge recharge" not in out


def test_registry_lists_read_tools():
    names = [t.info.name for t in registry.telco_tools()]
    assert len(names) == 17
    assert set(names) == {
        "get_account_summary",
        "get_usage_breakdown",
        "explain_deductions",
        "search_packages",
        "recommend_packages",
        "lookup_transactions",
        "get_offers_and_points",
        "get_case_status",
        "check_network_status",
        "find_care_centre",
        "purchase_package",
        "start_recharge",
        "redeem_reward",
        "verify_otp",
        "cancel_pending_action",
        "create_support_case",
        "request_human_agent",
    }


def test_each_list_suggests_a_new_way_to_offer_the_rest():
    from app.agent.tools import _common

    hints = [_common.listed(["- a", "- b", "- c", "- d"], 4)[-1] for _ in range(30)]
    assert all("To offer the rest" in h for h in hints)
    assert all(a != b for a, b in zip(hints, hints[1:]))
    assert len(set(hints)) > 3
    assert not _common.listed(["- a", "- b"], 2)[-1].startswith("Name")

