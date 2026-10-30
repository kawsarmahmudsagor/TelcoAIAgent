"""Whether a package auto-renews reaches the agent's tool text and the package card."""

from decimal import Decimal

from app.agent.tools.packages import _card, describe_package
from app.bss.types import PackageView
from app.models.telco import PackageKind


def _pack(auto_renewable: bool) -> PackageView:
    return PackageView(
        code="D15-30D", name="15 GB Monthly", kind=PackageKind.data, data_mb=15360, minutes=0,
        sms=0, validity_days=30, price=Decimal("349"), tag=None, auto_renewable=auto_renewable,
    )  # fmt: skip


def test_auto_renewable_package():
    p = _pack(True)
    assert describe_package(p).endswith("auto-renews at expiry from the main balance (hotline 121 turns it off)")
    assert _card(p)["auto_renewable"] is True


def test_package_that_does_not_auto_renew():
    p = _pack(False)
    assert describe_package(p).endswith("does not auto-renew (bought again when it ends)")
    assert _card(p)["auto_renewable"] is False
