"""The per-session context loaded once when a conversation starts: the account
snapshot placed in the system prompt, the customer's first name for the
greeting, and the wording of the proactive nudge that opened the session.

English facts for the LLM, like tool output. A missing or unknown subscriber is
a guest; a nudge counts only when it belongs to the session's subscriber.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.agent.telco_format import format_amount, format_data, format_day
from app.bss import accounts, network
from app.bss.clock import utc_now
from app.bss.errors import SubscriberNotFound
from app.bss.types import AccountSummary
from app.db.session import SessionLocal
from app.models.telco import Notification, NotificationKind, PlanType

GUEST_SNAPSHOT = """\
ACCOUNT SNAPSHOT — none: the customer is not logged in (a guest). You can still talk about
packages, offers, network status and general questions. For anything about their own account
(balance, packs, recharge, transactions, cases), ask them to log in first; never ask for their
number or any code to identify them."""

_SNAPSHOT_HEAD = """\
ACCOUNT SNAPSHOT — sample demo data, taken when this conversation started. Use it for quick
answers; call a tool for details, and after any change trust the tool's figures over these."""


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
        try:
            summary = accounts.get_account_summary(db, subscriber_id, now=now)
        except SubscriberNotFound:
            return GUEST
        incidents = network.check_network_status(db, summary.district, now=now)
        return SessionContext(
            subscriber_id=summary.subscriber_id,
            customer_name=_first_name(summary.full_name),
            snapshot=_snapshot_text(summary, incidents),
            nudge_text=_nudge_text(db, subscriber_id, nudge_id),
        )
    finally:
        db.close()


def _first_name(full_name: str) -> str | None:
    parts = full_name.split()
    return parts[0] if parts else None


def _snapshot_text(s: AccountSummary, incidents: list) -> str:
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
            lines.append(
                f"- {v.package_name}: {format_data(v.data_left_mb)} data, {v.minutes_left} minutes, "
                f"{v.sms_left} SMS left, expires {format_day(v.expires_at)}{renew}."
            )
    else:
        lines.append("No active packs.")
    lines.append(f"Reward points: {s.reward_points:,}.")
    lines.append(f"Open support cases: {s.open_cases}.")
    if incidents:
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
    news = f" is now {status}" if status else " has an update"
    return f"{case}{news}; offer to go through it with them"


_NUDGE_TEXT = {
    NotificationKind.pack_expiring: _pack_expiring,
    NotificationKind.low_balance: _low_balance,
    NotificationKind.low_data: _low_data,
    NotificationKind.case_update: _case_update,
}
