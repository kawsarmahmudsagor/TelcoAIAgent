"""Taka amounts worded the way the LLM should say them. The LLM copies the form
it's given, so a sale price handed over as "10,600,000 taka" comes back as
"106 lakh" or with a conversion in brackets; given "1 crore 6 lakh taka" it
says that."""

_LAKH = 100_000
_CRORE = 100 * _LAKH
# Rents stay below this and sale prices above it.
_SALE_FROM = 10 * _LAKH


def format_taka(amount: float, *, sale: bool | None = None) -> str:
    """Sale amounts in crore/lakh ("1 crore 6 lakh taka", "95 lakh taka"), rents
    and small amounts with thousands separators ("17,500 taka"). sale=None
    decides by size."""
    value = float(amount)
    if sale is None:
        sale = value >= _SALE_FROM
    if not sale or value < _LAKH:
        return f"{value:,.0f} taka"
    crore, rest = divmod(value, _CRORE)
    lakh = round(rest / _LAKH, 2)
    if lakh == 100:  # 1,99,99,999 rounds up to a whole crore
        crore, lakh = crore + 1, 0
    parts = []
    if crore:
        parts.append(f"{crore:.0f} crore")
    if lakh:
        parts.append(f"{lakh:g} lakh")
    return " ".join(parts) + " taka"
