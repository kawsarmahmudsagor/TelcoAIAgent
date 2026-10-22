"""Money, data and date wording for tool output (English facts for the LLM)."""

from datetime import datetime
from decimal import Decimal

from app.bss.clock import local_tz


def format_amount(amount: Decimal) -> str:
    """486.5 -> '486.50 taka'; whole amounts drop the decimals."""
    amount = Decimal(amount)
    if amount == amount.to_integral_value():
        return f"{int(amount):,} taka"
    return f"{amount:,.2f} taka"


def format_data(mb: int) -> str:
    """Under 1 GB in MB, else GB with one decimal ('.0' dropped)."""
    if mb < 1024:
        return f"{mb} MB"
    gb = f"{mb / 1024:.1f}"
    return f"{gb.removesuffix('.0')} GB"


def format_day(when: datetime, *, with_time: bool = False) -> str:
    """'Friday 24 October' in Asia/Dhaka; with_time adds ', 14:30'."""
    local = when.astimezone(local_tz())
    out = f"{local:%A} {local.day} {local:%B}"
    if with_time:
        out += f", {local:%H:%M}"
    return out
