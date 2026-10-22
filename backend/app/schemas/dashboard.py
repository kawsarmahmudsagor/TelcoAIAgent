from datetime import date
from typing import Literal

from pydantic import BaseModel


class DashboardSummary(BaseModel):
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
