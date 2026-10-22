from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.config import get_settings


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def local_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().agency_timezone)


def local_day_start(day: date) -> datetime:
    """UTC instant at which local `day` begins."""
    return datetime.combine(day, time.min, tzinfo=local_tz()).astimezone(timezone.utc)


def local_day_bounds(now: datetime) -> tuple[datetime, datetime]:
    """UTC [start, end) bounds of the local day containing `now`."""
    day = now.astimezone(local_tz()).date()
    return local_day_start(day), local_day_start(day + timedelta(days=1))
