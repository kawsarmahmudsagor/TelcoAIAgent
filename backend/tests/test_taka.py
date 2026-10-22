"""Sale prices are handed to the LLM in crore/lakh, the form it should say."""

import pytest

from app.services.taka import format_taka


@pytest.mark.parametrize(
    "amount, sale, expected",
    [
        (10_600_000, True, "1 crore 6 lakh taka"),
        (18_300_000, True, "1 crore 83 lakh taka"),
        (20_000_000, True, "2 crore taka"),
        (14_250_000, True, "1 crore 42.5 lakh taka"),
        (9_500_000, True, "95 lakh taka"),
        (500_000, True, "5 lakh taka"),
        (17_500, False, "17,500 taka"),
        (17_500, None, "17,500 taka"),
        (150_000, None, "150,000 taka"),
        (3_400_000, None, "34 lakh taka"),
        (19_999_999, True, "2 crore taka"),
    ],
)
def test_format_taka(amount, sale, expected):
    assert format_taka(amount, sale=sale) == expected
