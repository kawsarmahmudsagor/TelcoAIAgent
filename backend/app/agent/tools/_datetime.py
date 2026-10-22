from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from livekit.agents.llm import ToolError
from num2words import num2words

from app.config import get_settings


def agency_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().agency_timezone)


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
