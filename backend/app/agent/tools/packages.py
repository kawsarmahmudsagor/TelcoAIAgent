"""Package tools: search the catalogue, recommend by usage, buy (OTP-gated)."""

from __future__ import annotations

from decimal import Decimal

from livekit.agents import RunContext, function_tool
from livekit.agents.llm import ToolError
from sqlalchemy.orm import Session

from app.agent import actions
from app.agent.telco_format import format_amount, format_data
from app.agent.tools._common import error_text, parse_enum, run_db, run_read, run_write
from app.agent.userdata import SessionUserdata
from app.bss import accounts, packages
from app.bss.errors import BssError, InsufficientBalance, InvalidRequest
from app.bss.types import PackageView, PurchaseRequest
from app.models.telco import PackageKind, TxnChannel

_DETAIL = 3


def describe_package(p: PackageView) -> str:
    parts = []
    if p.data_mb:
        parts.append(format_data(p.data_mb))
    if p.minutes:
        parts.append(f"{p.minutes} minutes")
    if p.sms:
        parts.append(f"{p.sms} SMS")
    contents = ", ".join(parts) or "no allowance"
    return f"{p.name} (code {p.code}): {contents}, {p.validity_days} days, {format_amount(p.price)}"


def search_packages_text(
    db: Session,
    kind: str | None = None,
    max_price: float | None = None,
    min_data_gb: float | None = None,
    validity_days: int | None = None,
) -> str:
    """The catalogue search as tool text; raises BssError on a bad `kind`."""
    found = packages.search(
        db,
        kind=parse_enum(PackageKind, kind),
        max_price=None if max_price is None else Decimal(str(max_price)),
        min_data_gb=min_data_gb,
        validity_days=validity_days,
    )
    if not found:
        return "No packages match. Offer to widen the search (higher price or fewer filters)."
    lines = [f"{len(found)} matching packages, cheapest first:"]
    lines += [f"- {describe_package(p)}." for p in found[:_DETAIL]]
    if len(found) > _DETAIL:
        lines.append(f"{len(found) - _DETAIL} more not listed; offer to narrow the search.")
    return "\n".join(lines)


async def run_search_packages(
    userdata: SessionUserdata,
    kind: str | None = None,
    max_price: float | None = None,
    min_data_gb: float | None = None,
    validity_days: int | None = None,
) -> str:
    # The public catalogue: no subscriber needed.
    try:
        return await run_db(
            lambda db: search_packages_text(db, kind, max_price, min_data_gb, validity_days)
        )
    except BssError as err:
        raise ToolError(error_text(err)) from err


async def run_recommend_packages(userdata: SessionUserdata) -> str:
    def build(db, sid):
        recs = packages.recommend(db, sid)
        if not recs:
            return "No packages to recommend right now."
        lines = ["Best fits for their recent usage:"]
        lines += [f"- {describe_package(r.package)}. {r.reason}." for r in recs[:_DETAIL]]
        return "\n".join(lines)

    return await run_read(userdata, build, verify=True)


def _shortfall(db: Session, sid, package_code: str) -> Decimal:
    price = next(p.price for p in packages.search(db) if p.code == package_code)
    return price - accounts.get_account_summary(db, sid).main_balance


async def run_purchase_package(
    userdata: SessionUserdata, package_code: str, pay_from: str = "balance"
) -> str:
    async def call() -> str:
        channel = parse_enum(TxnChannel, pay_from)
        if channel is None:
            raise InvalidRequest("pay_from is required")
        req = PurchaseRequest(package_code=package_code.strip(), pay_from=channel)
        try:
            return await actions.start_action(userdata, "purchase", req)
        except InsufficientBalance as err:
            short = await run_db(lambda db: _shortfall(db, userdata.subscriber_id, req.package_code))
            raise ToolError(
                f"{error_text(err)} They are {format_amount(short)} short. "
                "Offer a recharge first (start_recharge)."
            ) from err

    return await run_write(userdata, call)


@function_tool(name="search_packages")
async def search_packages(
    ctx: RunContext[SessionUserdata],
    kind: str | None = None,
    max_price: float | None = None,
    min_data_gb: float | None = None,
    validity_days: int | None = None,
) -> str:
    """Search the active package catalogue (works for anyone, no login needed).
    Returns the cheapest matches first; only the first three are described.

    Args:
        kind: Optional: "data", "voice", "bundle" or "sms".
        max_price: Optional maximum price in taka.
        min_data_gb: Optional minimum data in GB.
        validity_days: Optional exact validity in days (e.g. 7 or 30).
    """
    return await run_search_packages(ctx.userdata, kind, max_price, min_data_gb, validity_days)


@function_tool(name="recommend_packages")
async def recommend_packages(ctx: RunContext[SessionUserdata]) -> str:
    """Recommend up to three packages that fit the customer's last 30 days of use."""
    return await run_recommend_packages(ctx.userdata)


@function_tool(name="purchase_package")
async def purchase_package(
    ctx: RunContext[SessionUserdata], package_code: str, pay_from: str = "balance"
) -> str:
    """Start buying a package for the customer. Nothing is charged yet: this
    quotes the price and sends a 6-digit code to their screen; the purchase
    happens only after verify_otp (or the Confirm button) succeeds.

    Args:
        package_code: The package code from search_packages or recommend_packages.
        pay_from: "balance" (default), "bkash", "nagad" or "card".
    """
    return await run_purchase_package(ctx.userdata, package_code, pay_from)
