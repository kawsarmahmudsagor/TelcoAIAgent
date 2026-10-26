"""The per-session context loaded when a conversation starts: the account
snapshot placed in the system prompt, the customer's first name for the
greeting, and the wording of the proactive nudge that opened the session.
load_snapshot re-reads the snapshot alone during the session
(app.agent.snapshot_refresh).

English facts for the LLM, like tool output. A missing or unknown subscriber is
a guest; a nudge counts only when it belongs to the session's subscriber.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.agent import highlights
from app.agent.telco_format import format_amount, format_data, format_day
from app.bss import accounts, network
from app.bss.notifications import case_status_words
from app.bss.clock import local_tz, utc_now
from app.bss.errors import SubscriberNotFound
from app.bss.types import AccountSummary
from app.db.session import SessionLocal
from app.models.telco import Notification, NotificationKind, PlanType

logger = logging.getLogger("agent.snapshot")

GUEST_SNAPSHOT = """\
ACCOUNT SNAPSHOT — none: the customer is not logged in (a guest). You can still talk about
packages, network status (ask which district they are in) and general questions. For anything
about their own account (balance, packs, recharge, offers and reward points, transactions,
cases), tell them to log in with the "Log in" button at the top of the page and that you'll answer
straight after, then offer one thing you can do now (find a pack, check the network, SIM or store
questions). They can browse packs, but buying, recharging or redeeming needs a login too: when a
guest likes a pack, say so instead of asking which one to buy. Never ask for their number or any
code to identify them."""

_SNAPSHOT_HEAD = """\
ACCOUNT SNAPSHOT — sample demo data, re-read from the account each time the customer speaks.
Answer balance, data, minutes, SMS, pack and points questions from it directly, no tool call.
Usage history, transactions and offers need their tools; right after a change, trust the tool's
figures over these."""


@dataclass(frozen=True)
class SessionContext:
    subscriber_id: UUID | None  # None when the id was missing or unknown (guest)
    customer_name: str | None  # first name
    snapshot: str  # GUEST_SNAPSHOT for guests
    nudge_text: str | None


GUEST = SessionContext(subscriber_id=None, customer_name=None, snapshot=GUEST_SNAPSHOT, nudge_text=None)


def load_session_context(
    subscriber_id: UUID | None, nudge_id: UUID | None, *, now: datetime | None = None
) -> SessionContext:
    """Sync (own DB session); the entrypoint runs it in a thread."""
    if subscriber_id is None:
        return GUEST
    now = now or utc_now()
    db = SessionLocal()
    try:
        read = _read_snapshot(db, subscriber_id, now)
        if read is None:
            return GUEST
        summary, snapshot = read
        return SessionContext(
            subscriber_id=summary.subscriber_id,
            customer_name=_first_name(summary.full_name),
            snapshot=snapshot,
            nudge_text=_nudge_text(db, subscriber_id, nudge_id),
        )
    finally:
        db.close()


def load_snapshot(subscriber_id: UUID, *, now: datetime | None = None) -> str | None:
    """The account snapshot as the DB has it now; None for an unknown
    subscriber. Sync (own DB session), for a worker thread."""
    db = SessionLocal()
    try:
        read = _read_snapshot(db, subscriber_id, now or utc_now())
        return read[1] if read is not None else None
    finally:
        db.close()


def _read_snapshot(
    db: Session, subscriber_id: UUID, now: datetime
) -> tuple[AccountSummary, str] | None:
    try:
        summary = accounts.get_account_summary(db, subscriber_id, now=now)
    except SubscriberNotFound:
        return None
    try:
        incidents = network.check_network_status(db, summary.district, now=now)
    except Exception:
        logger.exception("network status lookup failed; keeping the customer logged in")
        incidents = None
    try:
        # Answers come from the snapshot, so it gets the same notes and hooks as the tool.
        note = highlights.points_note(db, subscriber_id, summary.reward_points, now)
        extra = highlights.block(highlights.account_highlights(db, summary, now))
    except Exception:
        logger.exception("account highlights failed; snapshot without them")
        note, extra = "", ""
    return summary, _snapshot_text(summary, incidents, now, note) + extra


def _first_name(full_name: str) -> str | None:
    parts = full_name.split()
    return parts[0] if parts else None


def _snapshot_text(
    s: AccountSummary, incidents: list | None, now: datetime, points_note: str = ""
) -> str:
    today = now.astimezone(local_tz()).date()
    lines = [
        _SNAPSHOT_HEAD,
        f"Customer: {s.full_name}, number {s.masked_msisdn}, {s.plan_type.value}, "
        f"district {s.district}.",
    ]
    if s.plan_type == PlanType.prepaid:
        lines.append(f"Main balance: {format_amount(s.main_balance)}.")
    else:
        lines.append(f"Bill due: {format_amount(s.postpaid_due)}.")
    if s.subscriptions:
        lines.append("Active packs:")
        for v in s.subscriptions:
            renew = ", auto-renew on" if v.auto_renew else ""
            expires = format_day(v.expires_at)
            if when := highlights.relative_day(v.expires_at, today):
                expires = f"{when} ({expires})"
            lines.append(
                f"- {v.package_name}: {format_data(v.data_left_mb)} data, {v.minutes_left} minutes, "
                f"{v.sms_left} SMS left, expires {expires}{renew}."
            )
    else:
        lines.append("No active packs.")
    lines.append(f"Reward points: {s.reward_points:,}{points_note}.")
    lines.append(f"Open support cases: {s.open_cases}.")
    if incidents is None:
        lines.append(f"Network status in {s.district} is unavailable right now.")
    elif incidents:
        lines.append(f"Network incidents in {s.district}:")
        lines.extend(f"- {i.area}: {i.kind.value}, {i.status.value}." for i in incidents)
    else:
        lines.append(f"No network incidents in {s.district}.")
    return "\n".join(lines)


def _nudge_text(db: Session, subscriber_id: UUID, nudge_id: UUID | None) -> str | None:
    if nudge_id is None:
        return None
    row = db.get(Notification, nudge_id)
    if row is None or row.subscriber_id != subscriber_id:
        return None
    return _NUDGE_TEXT[row.kind](row.payload or {})


def _pack(p: dict[str, Any]) -> str:
    name = p.get("package_name")
    return f"their {name} pack" if name else "their pack"


def _day(p: dict[str, Any]) -> str:
    try:
        return f" on {format_day(datetime.fromisoformat(p['expires_at']))}"
    except (KeyError, TypeError, ValueError):
        return " soon"


def _money(raw: Any) -> str | None:
    try:
        return format_amount(Decimal(str(raw)))
    except (InvalidOperation, ValueError):
        return None


def _pack_expiring(p: dict[str, Any]) -> str:
    return f"{_pack(p)} expires{_day(p)} and auto-renew is off; offer to renew it or show similar packs"


def _low_balance(p: dict[str, Any]) -> str:
    amount = _money(p.get("balance"))
    left = f" (only {amount} left)" if amount else ""
    return f"their main balance is low{left}; offer to help them recharge"


def _low_data(p: dict[str, Any]) -> str:
    try:
        left = f", only {format_data(int(p['data_left_mb']))} left"
    except (KeyError, TypeError, ValueError):
        left = ""
    return f"{_pack(p)} is almost out of data{left}; offer a data pack"


def _case_update(p: dict[str, Any]) -> str:
    ref = p.get("case_ref")
    case = f"support case {ref}" if ref else "their support case"
    status = p.get("status")
    news = f" is {case_status_words(status)}" if status else " has an update"
    return f"{case}{news}; offer to go through it with them"


_NUDGE_TEXT = {
    NotificationKind.pack_expiring: _pack_expiring,
    NotificationKind.low_balance: _low_balance,
    NotificationKind.low_data: _low_data,
    NotificationKind.case_update: _case_update,
}
