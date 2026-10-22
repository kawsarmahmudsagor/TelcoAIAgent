from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.agent.telco_format import format_amount, format_data, format_day


@pytest.mark.parametrize(
    "value,expected",
    [(Decimal("486.5"), "486.50 taka"), (Decimal("500"), "500 taka"), (Decimal("1240"), "1,240 taka")],
)
def test_format_amount(value, expected):
    assert format_amount(value) == expected


@pytest.mark.parametrize("mb,expected", [(800, "800 MB"), (1024, "1 GB"), (15565, "15.2 GB")])
def test_format_data(mb, expected):
    assert format_data(mb) == expected


def test_format_day_uses_dhaka_time():
    when = datetime(2026, 10, 24, 8, 30, tzinfo=timezone.utc)  # 14:30 in Dhaka
    assert format_day(when) == "Saturday 24 October"
    assert format_day(when, with_time=True) == "Saturday 24 October, 14:30"


def test_format_day_rolls_over_to_local_date():
    when = datetime(2026, 10, 23, 19, 0, tzinfo=timezone.utc)  # 01:00 next day in Dhaka
    assert format_day(when) == "Saturday 24 October"
