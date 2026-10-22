import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from app.models.booking import BookingChannel, BookingStatus


class DashboardSummary(BaseModel):
    total_leads: int
    pending_calls_today: int
    bookings_this_week: int
    active_listings: int
    conversations_today: int
    # Knowledge base: searchable (ready/stale) sources out of all sources.
    kb_sources_ready: int
    kb_sources_total: int


class SeriesPoint(BaseModel):
    # Local calendar day in the agency timezone.
    date: date
    count: int


class ConversationSeries(BaseModel):
    range: Literal["7d", "30d", "90d"]
    timezone: str
    total: int
    points: list[SeriesPoint]


class RecentBooking(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    client_name: str | None
    property_id: uuid.UUID | None
    property_title: str | None
    channel: BookingChannel
    status: BookingStatus
    proposed_datetime: datetime
    created_at: datetime
