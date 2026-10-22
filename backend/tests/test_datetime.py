from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from livekit.agents.llm import ToolError

from app.agent.speech_numbers import numbers_to_bangla_words
from app.agent.tools._datetime import (
    check_viewing_hours,
    parse_future_local,
    spoken_local_bn,
    viewing_hours_text,
)

_DHAKA = ZoneInfo("Asia/Dhaka")


@pytest.mark.parametrize(
    ("when", "spoken"),
    [
        ((2026, 10, 14, 10, 0), "বুধবার, চৌদ্দ অক্টোবর, সকাল দশটায়"),
        ((2026, 10, 1, 14, 30), "বৃহস্পতিবার, পহেলা অক্টোবর, দুপুর আড়াইটায়"),
        ((2026, 10, 2, 13, 30), "শুক্রবার, দোসরা অক্টোবর, দুপুর দেড়টায়"),
        ((2026, 10, 21, 16, 30), "বুধবার, একুশ অক্টোবর, বিকাল সাড়ে চারটায়"),
        ((2026, 11, 3, 19, 45), "মঙ্গলবার, তেসরা নভেম্বর, সন্ধ্যা সাতটা পঁয়তাল্লিশ মিনিটে"),
    ],
)
def test_spoken_local_bn_says_the_time_in_bangla_words(when, spoken):
    assert spoken_local_bn(datetime(*when, tzinfo=_DHAKA)) == spoken


def test_spoken_local_bn_reads_utc_in_agency_time_and_leaves_no_digits():
    # 04:00 UTC is 10:00 in Dhaka.
    text = spoken_local_bn(datetime(2026, 10, 14, 4, 0, tzinfo=timezone.utc))
    assert text.endswith("সকাল দশটায়")
    assert "2026" not in text
    # The TTS number transform has nothing left to change.
    assert numbers_to_bangla_words(text) == text


def test_naive_time_is_agency_local():
    naive = (datetime.now() + timedelta(days=2)).replace(microsecond=0).isoformat()
    when = parse_future_local(naive, "when")
    assert when.utcoffset() == timedelta(hours=6)  # Asia/Dhaka, no DST


def test_explicit_offset_kept():
    aware = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    assert parse_future_local(aware, "when").utcoffset() == timedelta(0)


@pytest.mark.parametrize("value", ["2020-01-01T10:00:00", "not a date", ""])
def test_past_or_garbage_rejected(value):
    with pytest.raises(ToolError):
        parse_future_local(value, "when")


def _local(hour: int, minute: int = 0) -> datetime:
    day = datetime.now() + timedelta(days=2)
    return parse_future_local(day.replace(hour=hour, minute=minute, second=0, microsecond=0).isoformat(), "when")


@pytest.mark.parametrize(("hour", "minute"), [(8, 0), (11, 30), (17, 59), (18, 0)])
def test_viewing_hours_accept_8am_to_6pm(hour, minute):
    check_viewing_hours(_local(hour, minute), "proposed_datetime")


@pytest.mark.parametrize(("hour", "minute"), [(7, 59), (6, 0), (18, 1), (19, 0), (22, 30), (0, 0)])
def test_viewing_hours_reject_outside_8am_to_6pm(hour, minute):
    with pytest.raises(ToolError) as exc:
        check_viewing_hours(_local(hour, minute), "proposed_datetime")
    message = exc.value.message
    assert "8 AM to 6 PM" in message
    assert "another date" in message
    assert _local(hour, minute).strftime("%A %d %B") in message


def test_viewing_hours_use_agency_time():
    # 03:00 UTC is 09:00 in Dhaka: inside hours.
    day = (datetime.now(timezone.utc) + timedelta(days=2)).replace(hour=3, minute=0, second=0, microsecond=0)
    check_viewing_hours(day, "when")


def test_viewing_hours_text():
    assert viewing_hours_text() == "8 AM to 6 PM"
