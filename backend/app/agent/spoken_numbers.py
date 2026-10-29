"""Amounts a customer names, in whatever form speech-to-text wrote them:
"৩ জিবি", "3GB", "তিন জিবি", "থ্রি জিবি", "three GB", "উনসত্তর টাকা",
"একশো নয় টাকা", "one hundred and nine taka", "সাত দিনের".

The number words come from num2words (the same words app.agent.speech_numbers
speaks), read backwards, so every number up to a thousand is known in Bangla,
in English, and in English written in Bangla script, without a hand-kept list.
"""

import itertools
import re
import unicodedata
from functools import cache

from num2words import num2words

from app.agent.speech_numbers import _ENGLISH_IN_BENGALI

_TO_ASCII_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_MAX = 1000
# The longest number in words: "নয়শত নিরানব্বই", "nine hundred and ninety nine".
_MAX_TOKENS = 5

# num2words writes the teens one way ("পনের"); people and speech-to-text write
# them both ways ("পনেরো").
_BN_TEENS = {"এগার", "বার", "তের", "পনের", "ষোল", "সতের", "আঠার"}
_BN_HUNDRED = ("শত", "শো", "শ")

# What follows the number, by the start of the word ("জিবির", "টাকায়", "minutes").
_UNITS = (
    (("জিবি", "গিগা", "gb", "gig"), "data_mb", 1024),
    (("এমবি", "mb"), "data_mb", 1),
    (("মিনিট", "min"), "minutes", 1),
    (("এসএমএস", "sms"), "sms", 1),
    (("টাকা", "taka", "tk", "৳"), "price", 1),
    (("দিন", "day"), "validity_days", 1),
)

_TOKEN_RE = re.compile(r"[\d০-৯]+(?:\.[\d০-৯]+)?|৳|[^\s\d০-৯,।?!.()\-–—:;\"']+")


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def _bn_variants(words: str) -> list[str]:
    options = []
    for token in words.split():
        forms = {token}
        if token in _BN_TEENS:
            forms.add(token + "ো")
        if token.endswith("শত"):
            stem = token[: -len("শত")]
            forms |= {stem + h for h in _BN_HUNDRED}
            if stem == "দুই":
                forms |= {"দু" + h for h in _BN_HUNDRED}
        options.append(sorted(forms))
    variants = [" ".join(combo) for combo in itertools.product(*options)]
    # "এক হাজার" is said "হাজার" too.
    return variants + [v.removeprefix("এক ") for v in variants if v.startswith("এক হাজার")]


@cache
def _number_words() -> dict[str, int]:
    words: dict[str, int] = {}
    for n in range(1, _MAX + 1):
        for bn in _bn_variants(_nfc(num2words(n, lang="bn"))):
            words[bn] = n
        en = num2words(n, lang="en_IN").replace("-", " ").replace(",", "")
        for form in {en, en.replace(" and ", " ")}:
            words[form] = n
            words[" ".join(_ENGLISH_IN_BENGALI.get(w, w) for w in form.split())] = n
    return words


def _unit(word: str) -> tuple[str, int] | None:
    word = word.lower()
    for starts, field, scale in _UNITS:
        if word.startswith(starts):
            return field, scale
    return None


def named_amounts(text: str) -> set[tuple[str, float]]:
    """(field, amount) for each amount with a unit in `text`: ("data_mb", 3072)
    for "থ্রি জিবি", ("price", 69) for "উনসত্তর টাকা", ("minutes", 100)."""
    tokens = [t.lower() for t in _TOKEN_RE.findall(_nfc(text))]
    words = _number_words()
    found: set[tuple[str, float]] = set()
    i = 0
    while i < len(tokens):
        value, width = None, 0
        if tokens[i][0].isdigit():
            value, width = float(tokens[i].translate(_TO_ASCII_DIGITS)), 1
        else:
            for n in range(min(_MAX_TOKENS, len(tokens) - i), 0, -1):
                if (hit := words.get(" ".join(tokens[i : i + n]))) is not None:
                    value, width = float(hit), n
                    break
        if value is None:
            i += 1
            continue
        if i + width < len(tokens) and (unit := _unit(tokens[i + width])):
            field, scale = unit
            found.add((field, value * scale))
        i += width
    return found
