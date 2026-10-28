import re

import phonenumbers

from app.config import Settings

# Numbers typed without a country code ("01711-234567") are read as Bangladeshi,
# matching the agency's market.
_DEFAULT_REGION = "BD"


def normalize_e164(raw: str) -> str:
    """Returns `raw` as an E.164 string ("+8801711234567"), the only format SIP
    dialing accepts. Raises ValueError for anything that isn't a valid number."""
    try:
        parsed = phonenumbers.parse(raw, _DEFAULT_REGION)
    except phonenumbers.NumberParseException as exc:
        raise ValueError(f"{raw!r} is not a phone number") from exc
    if not phonenumbers.is_valid_number(parsed):
        raise ValueError(f"{raw!r} is not a valid phone number")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


# Bangla replies (and Bangla keyboards) write Bengali digits.
_BENGALI_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_MOBILE_TYPES = {
    phonenumbers.PhoneNumberType.MOBILE,
    phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE,
}


# A number said aloud reaches the agent as speech-to-text wrote it: "zero one
# seven triple zero ...", in English, Bangla or Banglish.
_DIGIT_WORDS = {
    digit: words.split()
    for digit, words in {
        "0": "zero oh o শূন্য শুন্য জিরো shunno shunnyo shunyo sunno",
        "1": "one এক ওয়ান ek",
        "2": "two দুই দু টু dui du",
        "3": "three তিন থ্রি tin teen",
        "4": "four চার ফোর char chaar",
        "5": "five পাঁচ ফাইভ panch pach",
        "6": "six ছয় ছয় ছ সিক্স choy chhoy",
        "7": "seven সাত সেভেন shat sat saat",
        "8": "eight আট এইট aat at",
        "9": "nine নয় নয় নাইন noy noi",
    }.items()
}
_WORD_TO_DIGIT = {word: digit for digit, words in _DIGIT_WORDS.items() for word in words}
_REPEAT_WORDS = {
    **dict.fromkeys(["double", "dobol", "dabol", "ডাবল"], 2),
    **dict.fromkeys(["triple", "tripple", "tripol", "ট্রিপল"], 3),
}
_SPOKEN_SPLIT_RE = re.compile(r"[\s,.\-]+")


def _spoken_digits(text: str) -> str:
    """ "zero one seven triple zero" -> "017000". Text with any word that isn't
    a digit or double/triple comes back unchanged, for the caller to reject."""
    digits = []
    repeat = 1
    for token in filter(None, _SPOKEN_SPLIT_RE.split(text.lower())):
        if token in _REPEAT_WORDS:
            repeat = _REPEAT_WORDS[token]
            continue
        digit = token if token.isdigit() or token == "+" else _WORD_TO_DIGIT.get(token)
        if digit is None:
            return text
        # "double 5", but not "double 55": a repeat covers one digit.
        digits.append(digit[0] * repeat + digit[1:])
        repeat = 1
    return "".join(digits)


_WORD_RE = re.compile(r"\S+")
# Punctuation around a word in a run ("seven," "eight.") is not part of the number.
_EDGE_PUNCT = ",.;:!?।\"'()"
_SENTENCE_END = (".", "!", "?", "।")
# A run this long is a phone number or a 6-digit code, not a count ("one or
# two bedrooms").
_MIN_SPOKEN_RUN = 6


def _is_spoken_digit(word: str) -> bool:
    word = word.lower().translate(_BENGALI_DIGITS)
    return word in _REPEAT_WORDS or word in _WORD_TO_DIGIT or word.isdigit()


def spoken_digits_in_text(text: str) -> str:
    """Writes a number said aloud as digits, the way speech-to-text can't: "my
    number is zero one seven zero one double zero one three nine eight" -> "my
    number is 01701001398". The LLM miscounts "double"/"triple" when it does
    this itself, so a caller's turn gets it done here first. Only a run of 6 or
    more digits changes; "one or two bedrooms" is left alone."""
    out, last = [], 0
    run: list[re.Match[str]] = []

    def flush() -> None:
        nonlocal last
        # A trailing "double" has no digit to repeat.
        while run and run[-1].group().strip(_EDGE_PUNCT).lower() in _REPEAT_WORDS:
            run.pop()
        if not run:
            return
        words = [m.group().strip(_EDGE_PUNCT).translate(_BENGALI_DIGITS) for m in run]
        digits = _spoken_digits(" ".join(words))
        if len(digits) >= _MIN_SPOKEN_RUN and digits.isdigit() and not all(w.isdigit() for w in words):
            first, end = run[0], run[-1]
            start = first.start() + len(first.group()) - len(first.group().lstrip(_EDGE_PUNCT))
            stop = end.end() - (len(end.group()) - len(end.group().rstrip(_EDGE_PUNCT)))
            out.append(text[last:start] + digits)
            last = stop
        run.clear()

    for match in _WORD_RE.finditer(text):
        word = match.group().strip(_EDGE_PUNCT)
        if word and _is_spoken_digit(word):
            run.append(match)
            if match.group().rstrip("\"')").endswith(_SENTENCE_END):
                # "two." ends its sentence: the next word starts a new run.
                flush()
        else:
            flush()
    flush()
    out.append(text[last:])
    return "".join(out)


def normalize_bd_mobile(raw: str | None) -> str:
    """A Bangladeshi mobile number in any common form ("01711-234567",
    "+880 1711 234567", "8801711234567", Bengali digits, or said aloud as words)
    as E.164 ("+8801711234567"). Raises ValueError for anything else, a foreign
    or landline number included."""
    text = (raw or "").translate(_BENGALI_DIGITS).strip()
    if any(c.isalpha() for c in text):
        text = _spoken_digits(text)
    e164 = normalize_e164(text)
    parsed = phonenumbers.parse(e164)
    if (
        phonenumbers.region_code_for_number(parsed) != _DEFAULT_REGION
        or phonenumbers.number_type(parsed) not in _MOBILE_TYPES
    ):
        raise ValueError(f"{raw!r} is not a Bangladeshi mobile number")
    return e164


def bd_mobile_local(e164: str) -> str:
    """"+8801711234567" -> "01711234567", the way people say and type it."""
    return "0" + e164.removeprefix("+880")


def dial_allowlist(settings: Settings) -> set[str]:
    """SIP_DIAL_ALLOWLIST, normalized so "01711..." and "+8801711..." match.
    Invalid entries are dropped rather than crashing the caller."""
    allowed = set()
    for entry in settings.sip_dial_allowlist.split(","):
        if entry.strip():
            try:
                allowed.add(normalize_e164(entry.strip()))
            except ValueError:
                continue
    return allowed


def is_dial_allowed(e164: str, settings: Settings) -> bool:
    """Empty allowlist means nothing may be dialed."""
    return e164 in dial_allowlist(settings)
