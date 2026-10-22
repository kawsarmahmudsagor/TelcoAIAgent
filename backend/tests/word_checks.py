"""Words left over from the real-estate agent this was forked from; customer-facing
copy (prompts, greetings, tool text) must contain none of them."""

import re

REAL_ESTATE_WORDS = (
    "apartment",
    "listing",
    "property",
    "viewing",
    "realty",
    "agency",
    "lakh",
    "flat",
    "ফ্ল্যাট",
    "ভিউয়িং",
)

# English words match whole words, case-insensitively, with an optional plural
# ("listings" counts, "flatten" doesn't). Bangla words match as substrings:
# \b is unreliable around Bengali vowel signs, and inflections attach directly
# ("ফ্ল্যাটের").
def _plural(word: str) -> str:
    return f"{word[:-1]}(?:y|ies)" if word.endswith("y") else f"{word}s?"


_ENGLISH = re.compile(
    r"\b(?:" + "|".join(_plural(w) for w in REAL_ESTATE_WORDS if w.isascii()) + r")\b",
    re.IGNORECASE,
)
_BANGLA = tuple(w for w in REAL_ESTATE_WORDS if not w.isascii())


def real_estate_words(text: str) -> list[str]:
    """The real-estate words found in `text`, empty when clean."""
    found = [m.group(0) for m in _ENGLISH.finditer(text)]
    found += [w for w in _BANGLA if w in text]
    return found
