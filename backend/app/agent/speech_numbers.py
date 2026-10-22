"""TTS text transform that spells numbers out as whole words.

Depending on the provider, TTS engines read bare digit runs like "2500000" or
"25,000" digit-by-digit ("two five zero zero..."). Converting them to words
before synthesis makes prices, sizes and counts sound the way a person says
them. The agent always writes digits; a Bangla reply gets Bangla number words
and an English one English words. The agent is told to answer Banglish in Bangla
script, but when it writes Banglish in English letters anyway, its words give it
away and the numbers are still said in Bangla. Only the TTS input is changed --
the chat transcript keeps the digits.
"""

import itertools
import re
from collections.abc import AsyncIterable, Callable

from num2words import num2words

# en_IN groups large numbers as lakh/crore, matching how Dhaka prices are said;
# "bn" does the same in Bangla (2500000 -> "পঁচিশ লাখ").
_EN = "en_IN"
_BN = "bn"

# Bengali vowel signs and marks aren't \w, so \b can't end a word after them.
_WORD_END = r"(?![\wঀ-৿])"

# Bangla ordinal suffixes: ১ম, ২য় (য় as one code point or two), ৪র্থ, ৬ষ্ঠ.
_BN_ORD_SUFFIX = "ম|য়|য়|র্থ|ষ্ঠ"

_TOKEN_RE = re.compile(
    # phone-like -- read out digit by digit in English (_speak_phone), in every language
    # (in Bangla script in a Bangla reply, _english_words):
    # an international prefix; "880…" without its "+"; a leading-zero local number, unbroken
    # or split by spaces/dashes ("01712 345678", up to 11 digits so a number after it stays
    # a number); a mobile number missing its leading zero ("1712345678" -- prices are
    # written with lakh/crore, never as a bare 10-digit run); or dash-separated groups
    r"(?P<phone>\+\d[\d\- ]*\d"
    r"|(?<![\d,.])[8৮]{2}[0০](?:[\- ]?\d){10}(?!\d)"
    r"|(?<![\d,.])[0০]\d(?:[\- ]?\d){4,9}(?!\d)"
    r"|(?<![\d,.])[0০]\d{5,}(?!\d)"
    r"|(?<![\d,.])[1১][3-9৩-৯]\d{8}(?!\d)"
    r"|(?<![\d,.])\d{2,5}(?:-\d{2,5}){2,}(?!\d))"
    r"|(?<![\d,.:])(?P<hour>\d{1,2}):(?P<minute>\d{2})(?![\d:])"
    r"|(?<![\d,.])(?P<num>\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?!\d)"
    rf"(?:(?P<ord>st|nd|rd|th)(?![A-Za-z])|(?P<bn_ord>{_BN_ORD_SUFFIX}){_WORD_END})?"
)

# "৳25,000" / "৳25 lakh" -> "25,000 taka" / "25 lakh taka", so the amount is then
# spoken as words with the currency after it, the way it's said aloud.
_TAKA_RE = re.compile(
    r"৳\s*(?P<amount>(?:\d{1,3}(?:,\d{2,3})+|\d+)(?:\.\d+)?)"
    rf"(?P<unit>\s*(?:lakh|crore|লাখ|কোটি|হাজার){_WORD_END})?",
    re.I,
)

# "106 lakh" -> "1 crore 6 lakh": the LLM is told to write crore from 100 lakh up,
# and this keeps the voice right when it doesn't.
_LAKH_RE = re.compile(
    rf"(?<![\d,.])(?P<lakh>\d+(?:\.\d+)?)\s*(?P<unit>lakh|লাখ|লক্ষ){_WORD_END}", re.I
)
_CRORE_WORD = {"lakh": "crore", "লাখ": "কোটি", "লক্ষ": "কোটি"}

# A number that may still be growing in the next streamed chunk ("25" -> ",000"),
# a "৳" whose amount hasn't arrived yet, or a phone number split by spaces
# ("+880 ", "01712 " -> "345678"). In Bangla a number's suffix can span chunks ("৪র" -> "্থ").
# A number followed by a word still arriving is held too, so "106 lakh" reaches
# _LAKH_RE whole.
_HOLDBACK_RE = re.compile(
    r"(?:\+[\d\- ]*|(?:৳\s*)?\d[\d,.:\- ]*(?:[A-Za-z]?|\s[A-Za-z]*)|৳\s*)\Z"
)
# In Bangla a capitalised English word is held too, with the number after it, so
# an address label reaches _LABELLED_NUMBER_RE together with its number.
_LABEL = r"(?<![A-Za-z])[A-Z][A-Za-z]*\.?"
_BN_HOLDBACK_RE = re.compile(
    rf"(?:\+[\d\- ]*|(?:{_LABEL}\s+)?(?:৳\s*)?\d[\d,.:\- ]*(?:[A-Za-z]?|[ঀ-৿]*|\s[A-Za-zঀ-৿]*)"
    rf"|৳\s*|{_LABEL}\s*)\Z"
)
_TRAILING_LABEL_RE = re.compile(rf"{_LABEL}\s*\Z")

# A number right after a capitalised English word is part of something written in
# English -- an address ("House 12, Road 7, Gulshan 1, Dhaka 1212"), "Sector 7" --
# and is said in English even in a Bangla reply. Not one starting with 0 (a phone
# number) or longer than 4 digits; a 4-digit one is a postcode, said digit by digit.
_LABELLED_NUMBER_RE = re.compile(
    rf"(?P<label>{_LABEL}\s+)(?P<num>[1-9১-৯][0-9০-৯]{{0,3}})"
    r"(?![0-9০-৯]|[,.:][0-9০-৯]|[A-Za-zঀ-৿])"
)

# The Bengali block minus U+09F3 "৳": English replies quote prices with the taka
# sign, and they must not be mistaken for Bangla.
_BENGALI_RE = re.compile("[ঀ-৲৴-৿]")

# Words that mark a reply as Banglish (Bangla in English letters). Only words that
# aren't also English ("ache", "din", "pore", "eta" are left out).
_BANGLISH_WORDS = frozenset(
    "apni apnar apnake apnader ami amar amake amra amader tumi tomar achhe nai nei "
    "hobe hoy hoye korte kore koren korun korben korbo chaile chan dite diye deben "
    "ebong kintu othoba shoho soho moddhe modhye jonno theke kemon koto kothay kono "
    "kichu ekta oita sheta ei oi tahole bhalo valo dekhte dekhben dekhun bolun "
    "bolben janaben janan jodi shathe sathe kache".split()
)  # fmt: skip
_LATIN_WORD_RE = re.compile(r"[A-Za-z]+")
# The end of the first sentence, after which a reply with no Banglish word is English.
_SENTENCE_END_RE = re.compile(r"[A-Za-z][^.!?]*[.!?]\s")
# Where the first number starts -- or a "৳"/"+" whose digits may still be coming.
_NUMBER_START_RE = re.compile(r"[৳+\d]")

# num2words has no Bangla ordinals.
_BN_ORDINALS = {
    1: "প্রথম", 2: "দ্বিতীয়", 3: "তৃতীয়", 4: "চতুর্থ", 5: "পঞ্চম",
    6: "ষষ্ঠ", 7: "সপ্তম", 8: "অষ্টম", 9: "নবম", 10: "দশম",
}  # fmt: skip


_DIGIT_WORDS = "zero one two three four five six seven eight nine".split()
_TO_ASCII_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_RUN_WORDS = {1: "{}", 2: "double {}", 3: "triple {}"}


def _digit_runs(digits: str) -> str:
    """Digits in English words, repeats grouped the way a number is said aloud:
    "001" -> "double zero one". Longer runs split into triples, ending on a
    double rather than a lone digit (4 -> double double, 7 -> triple double double)."""
    out: list[str] = []
    for digit, group in itertools.groupby(digits):
        word = _DIGIT_WORDS[int(digit)]
        n = len(list(group))
        while n:
            take = 2 if n == 4 else min(n, 3)
            out.append(_RUN_WORDS[take].format(word))
            n -= take
    return " ".join(out)


def _speak_phone(raw: str) -> str:
    """A phone number as said in Bangladesh, always in English: a mobile number's
    "zero one" and operator digit one by one, then the rest with doubles and
    triples -- "01701001398" -> "zero one seven zero one double zero one three
    nine eight". "+880 17…" (or "880 17…") is said as the local "017…"."""
    digits = re.sub(r"[^0-9]", "", raw.translate(_TO_ASCII_DIGITS))
    bd_mobile = digits.startswith("8801") and len(digits) == 13
    if raw.lstrip().startswith("+") and not bd_mobile:
        return "plus " + _digit_runs(digits)
    if bd_mobile:
        digits = "0" + digits[3:]
    if len(digits) == 11 and digits.startswith("01"):
        prefix = " ".join(_DIGIT_WORDS[int(d)] for d in digits[:3])
        return f"{prefix} {_digit_runs(digits[3:])}"
    return _digit_runs(digits)


# English number words in Bangla script. A Bangla reply's voice reads English words
# in Latin letters the Bangla way, so a phone number or an English address in one
# is handed over in Bangla script, said in English (like "পার্সেন্ট" below).
_ENGLISH_IN_BENGALI = {
    "zero": "জিরো", "one": "ওয়ান", "two": "টু", "three": "থ্রি", "four": "ফোর",
    "five": "ফাইভ", "six": "সিক্স", "seven": "সেভেন", "eight": "এইট", "nine": "নাইন",
    "ten": "টেন", "eleven": "ইলেভেন", "twelve": "টুয়েলভ", "thirteen": "থার্টিন",
    "fourteen": "ফোরটিন", "fifteen": "ফিফটিন", "sixteen": "সিক্সটিন",
    "seventeen": "সেভেনটিন", "eighteen": "এইটিন", "nineteen": "নাইনটিন",
    "twenty": "টুয়েন্টি", "thirty": "থার্টি", "forty": "ফোর্টি", "fifty": "ফিফটি",
    "sixty": "সিক্সটি", "seventy": "সেভেন্টি", "eighty": "এইটি", "ninety": "নাইন্টি",
    "hundred": "হান্ড্রেড", "thousand": "থাউজেন্ড", "and": "অ্যান্ড",
    "double": "ডাবল", "triple": "ট্রিপল", "plus": "প্লাস",
}  # fmt: skip


def _english_words(words: str, lang: str) -> str:
    """English number words as `lang`'s voice should get them."""
    if lang != _BN:
        return words
    return " ".join(_ENGLISH_IN_BENGALI.get(w, w) for w in re.split(r"[\s-]+", words))


def _words(value: int | float, lang: str, to: str = "cardinal") -> str:
    words = num2words(value, lang=lang, to=to).replace(",", "")
    # num2words writes hundreds the bookish way ("পাঁচশত"); people say "পাঁচশো".
    return words.replace("শত", "শো") if lang == _BN else words


def _replacer(lang: str) -> Callable[[re.Match[str]], str]:
    def replace(match: re.Match[str]) -> str:
        if phone := match.group("phone"):
            return _english_words(_speak_phone(phone), lang)

        if match.group("hour"):
            hour = _words(int(match.group("hour")), lang)
            minute = int(match.group("minute"))
            if minute == 0:
                return hour
            if minute < 10 and lang == _EN:
                return f"{hour} oh {_words(minute, lang)}"
            return f"{hour} {_words(minute, lang)}"

        raw = match.group("num").replace(",", "")
        value: int | float = float(raw) if "." in raw else int(raw)
        if bn_ord := match.group("bn_ord"):
            if isinstance(value, int) and value in _BN_ORDINALS:
                return _BN_ORDINALS[value]
            return _words(value, lang) + bn_ord
        if match.group("ord") and isinstance(value, int):
            # Bangla has no "2nd": say the plain number.
            return _words(value, lang, to="ordinal" if lang == _EN else "cardinal")
        return _words(value, lang) + (match.group("ord") or "")

    return replace


_REPLACE = {_EN: _replacer(_EN), _BN: _replacer(_BN)}
_TAKA_WORD = {_EN: "taka", _BN: "টাকা"}

# "10%" -> "10 percent" (ASCII, full-width and Arabic percent signs). Always said
# "percent", in Bangla and Banglish too (not "শতাংশ") -- in Bangla script there so
# the voice reads it the same way.
_PERCENT_RE = re.compile(r"\s*[%％٪]")
_PERCENT_WORD = {_EN: "percent", _BN: "পার্সেন্ট"}


def _lakh_as_crore(match: re.Match[str]) -> str:
    lakh = float(match.group("lakh"))
    if lakh < 100:
        return match.group(0)
    unit = match.group("unit")
    crore, rest = divmod(lakh, 100)
    out = f"{crore:.0f} {_CRORE_WORD[unit.lower()]}"
    rest = round(rest, 2)
    return f"{out} {rest:g} {unit}" if rest else out


def _labelled_number_in_english(match: re.Match[str]) -> str:
    digits = match.group("num").translate(_TO_ASCII_DIGITS)
    if len(digits) == 4:
        words = " ".join(_DIGIT_WORDS[int(d)] for d in digits)
    else:
        words = _words(int(digits), _EN)
    return match.group("label") + _english_words(words, _BN)


def _convert(text: str, lang: str) -> str:
    if lang == _BN:
        text = _LABELLED_NUMBER_RE.sub(_labelled_number_in_english, text)
    taka = _TAKA_WORD[lang]
    text = _TAKA_RE.sub(rf"\g<amount>\g<unit> {taka}", text).replace("৳", taka)
    text = _LAKH_RE.sub(_lakh_as_crore, text)
    text = _PERCENT_RE.sub(f" {_PERCENT_WORD[lang]}", text)
    return _TOKEN_RE.sub(_REPLACE[lang], text)


def numbers_to_words(text: str) -> str:
    """Replaces every number in `text` with its spoken English words, except phone numbers."""
    return _convert(text, _EN)


def numbers_to_bangla_words(text: str) -> str:
    """Replaces every number in `text` with its spoken Bangla words, except phone numbers."""
    return _convert(text, _BN)


def _reply_language(text: str, final: bool = False) -> str | None:
    """The language a reply's numbers are spoken in, or None while it's unclear."""
    if _BENGALI_RE.search(text):
        return _BN
    banglish = len({w.lower() for w in _LATIN_WORD_RE.findall(text)} & _BANGLISH_WORDS)
    if banglish >= 2:
        return _BN
    if final or _SENTENCE_END_RE.search(text):
        return _BN if banglish else _EN
    return None


async def speak_numbers_as_words(text: AsyncIterable[str]) -> AsyncIterable[str]:
    """Streaming `tts_text_transforms` entry for AgentSession.

    A reply's numbers are held back until its language is clear -- Bengali
    script, Banglish words, or the end of an English first sentence -- so a
    reply that opens with a number ("25 লাখ...", "28,000 taka ... shoho.") isn't
    read in English first. Text before the first number streams through.
    """
    buffer = ""
    seen = ""
    lang: str | None = None
    async for chunk in text:
        buffer += chunk
        if lang is None:
            seen += chunk
            lang = _reply_language(seen)
        if lang is None:
            # Text before the first number is the same in either language.
            number = _NUMBER_START_RE.search(buffer)
            flush_to = number.start() if number else len(buffer)
            # Keep a capitalised word with the number that may follow it.
            if label := _TRAILING_LABEL_RE.search(buffer[:flush_to]):
                flush_to = label.start()
            if flush_to > 0:
                yield buffer[:flush_to]
                buffer = buffer[flush_to:]
            continue

        held = (_BN_HOLDBACK_RE if lang == _BN else _HOLDBACK_RE).search(buffer)
        flush_to = held.start() if held else len(buffer)
        if flush_to > 0:
            yield _convert(buffer[:flush_to], lang)
            buffer = buffer[flush_to:]

    if buffer:
        yield _convert(buffer, lang or _reply_language(seen, final=True))
