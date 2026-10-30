"""Package tools: search the catalogue, recommend by usage, buy (OTP-gated)."""

from __future__ import annotations

import json
import unicodedata
from decimal import Decimal

from livekit.agents import RunContext, function_tool
from livekit.agents.llm import ToolError
from sqlalchemy.orm import Session

from app.agent import actions, cards
from app.agent.spoken_numbers import named_amounts
from app.agent.telco_format import format_amount, format_data
from app.agent.tools._common import (
    LISTED,
    error_text,
    listed,
    parse_enum,
    run_db,
    run_read,
    run_write,
)
from app.agent.topics import PACKAGES
from app.agent.userdata import SessionUserdata
from app.bss import accounts, packages
from app.bss.errors import BssError, InsufficientBalance, InvalidRequest
from app.bss.types import PackageView, PurchaseRequest
from app.models.telco import PackageKind, TxnChannel

_DETAIL = 3
_CARDS = 6


def _card(p: PackageView) -> dict:
    return {
        "code": p.code,
        "name": p.name,
        "kind": p.kind.value,
        "data_mb": p.data_mb,
        "minutes": p.minutes,
        "sms": p.sms,
        "validity_days": p.validity_days,
        "price": float(p.price),
        "tag": p.tag,
        "auto_renewable": p.auto_renewable,
    }


# Words of a package's name or tag as customers say them, so "থ্রি জিবি
# উইকএন্ড" finds "3 GB Weekend". Amounts are app.agent.spoken_numbers' job.
_NAME_WORDS = {
    "daily": ("daily", "ডেইলি", "দৈনিক"),
    "weekend": ("weekend", "উইকএন্ড", "উইকেন্ড"),
    "weekly": ("weekly", "উইকলি", "সাপ্তাহিক"),
    "monthly": ("monthly", "মান্থলি", "মাসিক"),
    "smart": ("smart", "স্মার্ট"),
    "starter": ("starter", "স্টার্টার"),
    "popular": ("popular", "পপুলার"),
    "premium": ("premium", "প্রিমিয়াম"),
    "exclusive": ("exclusive", "এক্সক্লুসিভ"),
}


def _named_words(text: str) -> set[str]:
    text = unicodedata.normalize("NFC", text).lower()
    return {
        word
        for word, said in _NAME_WORDS.items()
        if any(unicodedata.normalize("NFC", s) in text for s in said)
    }


def _matches(p: PackageView, amounts: set[tuple[str, float]], words: set[str]) -> int:
    """How many of the things the customer named this package has."""
    own = {
        "data_mb": p.data_mb, "minutes": p.minutes, "sms": p.sms, "price": float(p.price),
        "validity_days": p.validity_days,
    }
    label = f"{p.name} {p.tag or ''}".lower()
    return sum(own[field] == amount for field, amount in amounts) + sum(w in label for w in words)


def _about_turn(found: list[PackageView], text: str) -> list[PackageView]:
    """The packages that best fit what the customer named in this turn (size,
    price, name: "থ্রি জিবি উইকএন্ড উনসত্তর টাকা" is one package); all of
    them when they named nothing any package has."""
    amounts, words = named_amounts(text), _named_words(text)
    scores = [_matches(p, amounts, words) for p in found]
    best = max(scores, default=0)
    if best == 0:
        return found
    return [p for p, score in zip(found, scores) if score == best]


async def _publish_cards(userdata: SessionUserdata, title: str, found: list[PackageView]) -> None:
    """Cards for what this turn asks about, shown with the reply's first words
    (app.agent.cards). The set already on screen isn't sent again."""
    shown = _about_turn(found, userdata.turn_text)[:_CARDS]
    if not shown:
        return
    payload = json.dumps({"title": title, "packages": [_card(p) for p in shown]})
    if payload == userdata.shown_packages:
        return
    userdata.shown_packages = payload
    await cards.send_card(userdata, PACKAGES, payload)


def describe_package(p: PackageView) -> str:
    parts = []
    if p.data_mb:
        parts.append(format_data(p.data_mb))
    if p.minutes:
        parts.append(f"{p.minutes} minutes")
    if p.sms:
        parts.append(f"{p.sms} SMS")
    contents = ", ".join(parts) or "no allowance"
    renew = (
        "auto-renews at expiry from the main balance (hotline 121 turns it off)"
        if p.auto_renewable
        else "does not auto-renew (bought again when it ends)"
    )
    return (
        f"{p.name} (code {p.code}): {contents}, {p.validity_days} days, "
        f"{format_amount(p.price)}, {renew}"
    )


def _search(
    db: Session,
    kind: str | None,
    max_price: float | None,
    min_data_gb: float | None,
    validity_days: int | None,
) -> list[PackageView]:
    return packages.search(
        db,
        kind=parse_enum(PackageKind, kind),
        max_price=None if max_price is None else Decimal(str(max_price)),
        min_data_gb=min_data_gb,
        validity_days=validity_days,
    )


def _search_text(found: list[PackageView]) -> str:
    if not found:
        return "No packages match. Offer to widen the search (higher price or fewer filters)."
    lines = [f"{len(found)} matching packages, cheapest first:"]
    lines += listed([f"- {describe_package(p)}." for p in found[:LISTED]], len(found))
    return "\n".join(lines)


def search_packages_text(
    db: Session,
    kind: str | None = None,
    max_price: float | None = None,
    min_data_gb: float | None = None,
    validity_days: int | None = None,
) -> str:
    """The catalogue search as tool text; raises BssError on a bad `kind`."""
    return _search_text(_search(db, kind, max_price, min_data_gb, validity_days))


async def run_search_packages(
    userdata: SessionUserdata,
    kind: str | None = None,
    max_price: float | None = None,
    min_data_gb: float | None = None,
    validity_days: int | None = None,
) -> str:
    # The public catalogue: no subscriber needed.
    try:
        found = await run_db(lambda db: _search(db, kind, max_price, min_data_gb, validity_days))
    except BssError as err:
        raise ToolError(error_text(err)) from err
    await _publish_cards(userdata, "Packages", found)
    return _search_text(found)


async def run_recommend_packages(userdata: SessionUserdata) -> str:
    recs = []

    def build(db, sid):
        recs[:] = packages.recommend(db, sid)
        if not recs:
            return "No packages to recommend right now."
        lines = ["Best fits for their recent usage:"]
        lines += [f"- {describe_package(r.package)}. {r.reason}." for r in recs[:_DETAIL]]
        return "\n".join(lines)

    out = await run_read(userdata, build, verify=True)
    await _publish_cards(userdata, "Recommended for you", [r.package for r in recs])
    return out


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
        # Codes are upper case ("D8-7D"); the model may write "d8-7d".
        req = PurchaseRequest(package_code=package_code.strip().upper(), pay_from=channel)
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
    Returns up to ten matches, cheapest first; name them three at a time.

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
    happens only after verify_otp (or the confirm card, with the code) succeeds.

    Args:
        package_code: The package code from search_packages or recommend_packages.
        pay_from: "balance" (default), "bkash", "nagad" or "card".
    """
    return await run_purchase_package(ctx.userdata, package_code, pay_from)
