from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from livekit.agents.llm import ToolError
from num2words import num2words

from app.config import get_settings


def agency_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().agency_timezone)


def _hour_label(hour: int) -> str:
    """8 -> "8 AM", 18 -> "6 PM", 12 -> "12 PM", 0 and 24 -> "12 AM"."""
    suffix = "AM" if hour % 24 < 12 else "PM"
    return f"{hour % 12 or 12} {suffix}"


def viewing_hours_text(joiner: str = "to") -> str:
    """"8 AM to 6 PM" (or "8 AM and 6 PM" after "between"), from the settings."""
    settings = get_settings()
    start, end = _hour_label(settings.viewing_start_hour), _hour_label(settings.viewing_end_hour)
    return f"{start} {joiner} {end}"


def within_viewing_hours(when: datetime) -> bool:
    """Whether `when` (read in agency local time) is inside live viewing hours.
    Any day of the week is fine."""
    settings = get_settings()
    local = when.astimezone(agency_tz())
    minutes = local.hour * 60 + local.minute
    return settings.viewing_start_hour * 60 <= minutes <= settings.viewing_end_hour * 60


def check_viewing_hours(when: datetime, field: str) -> None:
    """Raises ToolError, telling the LLM what to say, when `when` (agency local
    time) is outside live viewing hours. Any day of the week is fine."""
    if within_viewing_hours(when):
        return
    local = when.astimezone(agency_tz())
    hours, between = viewing_hours_text(), viewing_hours_text("and")
    day = local.strftime("%A %d %B")
    raise ToolError(
        f"{field} {local.strftime('%H:%M')} is outside live viewing hours ({hours}, any day); "
        f"the time was not saved. Politely tell the customer that live viewings run from {hours}, "
        f"then ask whether any time between {between} on {day} would suit them, or whether they "
        f"would rather choose another date when they are free between {between}. If they have "
        f"already said they aren't free between {between} on {day}, don't ask about {day} "
        "again: acknowledge it and ask only about another day. Don't suggest a time outside "
        "those hours. Keep replying in the customer's language."
    )


def spoken_local(when: datetime) -> str:
    """A stored time as the agency reads it: "Wednesday 14 October 2026, 10:00"."""
    return when.astimezone(agency_tz()).strftime("%A %d %B %Y, %H:%M")


_BN_WEEKDAYS = ("সোমবার", "মঙ্গলবার", "বুধবার", "বৃহস্পতিবার", "শুক্রবার", "শনিবার", "রবিবার")
_BN_MONTHS = (
    "জানুয়ারি", "ফেব্রুয়ারি", "মার্চ", "এপ্রিল", "মে", "জুন",
    "জুলাই", "আগস্ট", "সেপ্টেম্বর", "অক্টোবর", "নভেম্বর", "ডিসেম্বর",
)  # fmt: skip
# The 1st to 4th of a month are said with their own words, not "এক অক্টোবর".
_BN_DAY_WORDS = {1: "পহেলা", 2: "দোসরা", 3: "তেসরা", 4: "চৌঠা"}
# 1:30 and 2:30 have their own words; any other half hour is "সাড়ে".
_BN_HALF_PAST = {1: "দেড়টায়", 2: "আড়াইটায়"}


def _bn_part_of_day(hour: int) -> str:
    if 4 <= hour < 6:
        return "ভোর"
    if 6 <= hour < 12:
        return "সকাল"
    if 12 <= hour < 15:
        return "দুপুর"
    if 15 <= hour < 18:
        return "বিকাল"
    if 18 <= hour < 20:
        return "সন্ধ্যা"
    return "রাত"


def spoken_local_bn(when: datetime) -> str:
    """A stored time as said aloud in Bangla, in the locative ("on/at"), for a
    line the TTS speaks word for word: "বুধবার, চৌদ্দ অক্টোবর, সকাল দশটায়". No
    year. Numbers are already words, so the TTS number transform leaves them be."""
    local = when.astimezone(agency_tz())
    day = _BN_DAY_WORDS.get(local.day) or num2words(local.day, lang="bn")
    date = f"{_BN_WEEKDAYS[local.weekday()]}, {day} {_BN_MONTHS[local.month - 1]}"
    hour12 = local.hour % 12 or 12
    hour = num2words(hour12, lang="bn")
    if local.minute == 0:
        clock = f"{hour}টায়"
    elif local.minute == 30:
        clock = _BN_HALF_PAST.get(hour12) or f"সাড়ে {hour}টায়"
    else:
        clock = f"{hour}টা {num2words(local.minute, lang='bn')} মিনিটে"
    return f"{date}, {_bn_part_of_day(local.hour)} {clock}"


def parse_future_local(value: str, field: str) -> datetime:
    """Parses an ISO 8601 date/time from the LLM into an aware datetime.

    The LLM is told times are local to the agency (persona.py), so a naive value
    gets the agency timezone attached -- storing it naive would leave Postgres to
    read it in whatever its session timezone happens to be. Rejects past times."""
    try:
        when = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ToolError(f"Could not parse {field}: {exc}") from exc
    if when.tzinfo is None:
        when = when.replace(tzinfo=agency_tz())
    if when < datetime.now(timezone.utc):
        raise ToolError("That date/time is in the past. Ask the customer for a future date and time.")
    return when
