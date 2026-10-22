from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_db
from app.api.routes_conversations import list_items
from app.config import get_settings
from app.models.call_schedule import CallScheduleEntry, CallStatus
from app.models.property import Property
from app.rag import index as rag_index
from app.repositories import agent_config_repo, booking_repo, client_repo, conversation_repo
from app.schemas.conversation import ConversationListItem
from app.schemas.dashboard import (
    ConversationSeries,
    DashboardSummary,
    RecentBooking,
    SeriesPoint,
)
from app.schemas.rag import RagSourceCounts, RagStatus
from app.services import agent_config_service, rag_service

router = APIRouter(
    prefix="/api/dashboard", tags=["dashboard"], dependencies=[Depends(get_current_admin)]
)

SERIES_DAYS = {"7d": 7, "30d": 30, "90d": 90}


# "Today" and the chart's days are the agency's calendar days, not UTC ones.


def _agency_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().agency_timezone)


def _local_midnight(day: date, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, time(), tzinfo=tz)


def local_today(tz: ZoneInfo, now: datetime | None = None) -> date:
    return (now or datetime.now(timezone.utc)).astimezone(tz).date()


def today_bounds(tz: ZoneInfo, now: datetime | None = None) -> tuple[datetime, datetime]:
    """[start, end) of the agency's current calendar day, as aware datetimes."""
    today = local_today(tz, now)
    return _local_midnight(today, tz), _local_midnight(today + timedelta(days=1), tz)


def week_start(tz: ZoneInfo, now: datetime | None = None) -> datetime:
    """Monday 00:00 of the agency's current week."""
    today = local_today(tz, now)
    return _local_midnight(today - timedelta(days=today.weekday()), tz)


def build_series(
    db: Session, days: int, tz: ZoneInfo, now: datetime | None = None
) -> list[SeriesPoint]:
    """One zero-filled point per local day, oldest first, ending today."""
    today = local_today(tz, now)
    first = today - timedelta(days=days - 1)
    counts = conversation_repo.daily_counts(
        db,
        _local_midnight(first, tz),
        _local_midnight(today + timedelta(days=1), tz),
        tz.key,
    )
    return [
        SeriesPoint(date=day, count=counts.get(day, 0))
        for day in (first + timedelta(days=offset) for offset in range(days))
    ]


@router.get("/summary", response_model=DashboardSummary)
def summary(db: Session = Depends(get_db)) -> DashboardSummary:
    tz = _agency_tz()
    today_start, today_end = today_bounds(tz)

    pending_today_stmt = (
        select(func.count())
        .select_from(CallScheduleEntry)
        .where(
            CallScheduleEntry.status == CallStatus.pending,
            CallScheduleEntry.scheduled_at >= today_start,
            CallScheduleEntry.scheduled_at < today_end,
        )
    )
    pending_calls_today = db.scalar(pending_today_stmt) or 0

    active_listings_stmt = (
        select(func.count()).select_from(Property).where(Property.is_active.is_(True))
    )
    active_listings = db.scalar(active_listings_stmt) or 0
    kb_counts = rag_service.status_counts(db)

    return DashboardSummary(
        total_leads=client_repo.count(db),
        pending_calls_today=pending_calls_today,
        bookings_this_week=booking_repo.count_created_since(db, week_start(tz)),
        active_listings=active_listings,
        conversations_today=conversation_repo.count_started_between(db, today_start, today_end),
        kb_sources_ready=sum(kb_counts[name] for name in rag_service.SEARCHABLE_STATUSES),
        kb_sources_total=sum(kb_counts.values()),
    )


@router.get("/rag-status", response_model=RagStatus)
def rag_status(db: Session = Depends(get_db)) -> RagStatus:
    row = agent_config_repo.get(db)
    config = agent_config_service.resolve(row)
    counts = rag_service.status_counts(db)
    jobs = rag_service.job_counts(db)
    return RagStatus(
        rag_enabled=config.rag_enabled,
        embedding_ready=bool(agent_config_service.embedding_api_key(config)),
        chroma_reachable=rag_index.heartbeat(),
        embedding_model=config.embedding_model,
        sources=RagSourceCounts(total=sum(counts.values()), **counts),
        total_chunks=rag_service.total_chunks(db),
        jobs_pending=jobs["pending"],
        jobs_processing=jobs["processing"],
        jobs_failed=jobs["failed"],
        embedding_migration_status=row.embedding_migration_status if row else None,
        embedding_migration_target=row.embedding_migration_target if row else None,
        embedding_migration_error=row.embedding_migration_error if row else None,
    )


@router.get("/conversation-series", response_model=ConversationSeries)
def conversation_series(
    db: Session = Depends(get_db),
    range_: Literal["7d", "30d", "90d"] = Query(default="7d", alias="range"),
) -> ConversationSeries:
    tz = _agency_tz()
    points = build_series(db, SERIES_DAYS[range_], tz)
    return ConversationSeries(
        range=range_, timezone=tz.key, total=sum(p.count for p in points), points=points
    )


@router.get("/recent-conversations", response_model=list[ConversationListItem])
def recent_conversations(
    db: Session = Depends(get_db), limit: int = Query(default=5, ge=1, le=20)
) -> list[ConversationListItem]:
    rows, _total = conversation_repo.list_page(db, limit=limit)
    return list_items(rows)


@router.get("/recent-bookings", response_model=list[RecentBooking])
def recent_bookings(
    db: Session = Depends(get_db), limit: int = Query(default=5, ge=1, le=20)
) -> list[RecentBooking]:
    return [
        RecentBooking(
            id=booking.id,
            client_id=booking.client_id,
            client_name=client_name,
            property_id=booking.property_id,
            property_title=property_title,
            channel=booking.channel,
            status=booking.status,
            proposed_datetime=booking.proposed_datetime,
            created_at=booking.created_at,
        )
        for booking, client_name, property_title in booking_repo.list_recent(db, limit=limit)
    ]
