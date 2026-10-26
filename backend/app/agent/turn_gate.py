"""Cheap, deterministic checks on a voice turn, plus the decision table that
combines them with the relevance judge's score.

Pure functions, no livekit imports, so they are unit-tested directly and shared
with scripts/judge_bench. The agent wiring lives in app.agent.gated_agent.
"""

import difflib
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

Script = Literal["bn", "en", "other", "none"]

# Split on whitespace and punctuation only: `\w` would cut Bengali words apart at
# their vowel signs (আমার -> আম, র), which are combining marks, not letters.
_SPLIT = re.compile(r"[\s।,.!?;:\"'()\[\]{}…\-–—/]+")

_FILLERS = {
    "uh", "um", "umm", "uhm", "hmm", "hm", "mm", "mmm", "mhm", "mm-hmm", "uh-huh", "ah", "oh",
    "eh", "er", "erm", "huh", "হুম", "হুঁ", "উম", "আ", "ও", "এ", "উহ", "হুমম", "হুঁম",
}

# The fillers that mean "yes, go on": a bare hum answering the agent's question
# is a reply, not noise. No uh-huh: _SPLIT cuts it into "uh" and "huh".
_ASSENT_FILLERS = {"hmm", "hm", "mm", "mmm", "mhm", "mm-hmm", "হুম", "হুঁ", "হুমম", "হুঁম"}

# Phrases a customer uses to cut the agent off; they interrupt without waiting
# for the judge. Matched at the start of the utterance.
_STOP_PHRASES = (
    "wait", "stop", "hold on", "one minute", "one sec", "one second", "excuse me", "no no",
    "থামুন", "থামো", "দাঁড়ান", "এক মিনিট", "এক সেকেন্ড", "শুনুন", "না না",
)

# Phrases a customer ends the conversation with. A short turn containing one is
# always accepted: Jev scores goodbyes low ("ঠিক আছে Tata bye bye" 0.24), and the
# agent has to hear them to say goodbye and end the call. Matched as whole words.
_CLOSING_PHRASES = (
    "bye", "goodbye", "good bye", "that's all", "that is all", "that's it", "nothing else",
    "no more questions", "any more help", "anymore help", "no more help",
    "don't need anything", "do not need anything", "thanks", "thank you", "thankyou",
    "see you", "take care", "have a nice day", "have a good day", "good night", "tata",
    "allah hafez", "khoda hafez", "dhonnobad", "dhonnobaad",
    "বাই", "টাটা", "আল্লাহ হাফেজ", "আল্লাহ হাফিজ", "খোদা হাফেজ", "ধন্যবাদ", "থ্যাংক ইউ",
    "থ্যাংকস", "আর কিছু লাগবে না", "আর কিছু না", "আর কিছু জানার নেই", "আর লাগবে না",
    "আর দরকার নেই", "আর কিছু দরকার নেই", "এটুকুই", "এই পর্যন্তই", "পরে কথা হবে",
    # Informal Bangla and Banglish sign-offs. Multi-word, so a lone "রাখি" or
    # "আসি" inside a request ("বাজেট ৫০ লাখ রাখি") isn't taken for a goodbye.
    "বাই বাই", "টা টা", "থ্যাঙ্ক ইউ", "থ্যাংক্স", "থ্যাঙ্কস", "আসি তাহলে", "তাহলে আসি",
    "আজ আসি", "আচ্ছা আসি", "রাখি তাহলে", "তাহলে রাখি", "এখন রাখি", "আচ্ছা রাখি", "এখন রাখছি",
    "ফোন রাখছি", "ভালো থাকবেন", "ভালো থাকেন", "ভালো থেকো", "পরে কথা বলব", "পরে কথা বলবো",
    "আজকের মতো এটুকুই", "bye bye", "ta ta", "ashi tahole", "tahole ashi", "rakhi tahole",
    "tahole rakhi", "bhalo thakben", "valo thakben", "pore kotha hobe", "pore kotha bolbo",
)  # fmt: skip
# Longer turns are left to the judge: a goodbye is short.
_CLOSING_MAX_WORDS = 8

# Bangla second-person pronouns: customers address the agent politely (আপনি);
# people in the room talk to each other with তুমি/তুই.
_FORMAL_WORDS = {"আপনি", "আপনার", "আপনাকে", "আপনারা", "আপনাদের"}
_INFORMAL_WORDS = {
    "তুমি", "তোমার", "তোমাকে", "তোমরা", "তোমাদের",
    "তুই", "তোর", "তোকে", "তোরা",
    "দাও", "করো", "বলো", "শোনো", "খোল", "খাও", "যাও", "দেখো",
}
# Polite verb endings (জানাবেন, শুনুন) vs the intimate -িস (করিস).
_FORMAL_ENDINGS = ("েন", "ুন")
_INFORMAL_ENDINGS = ("িস",)


# Non-speech sounds the STT writes as tags: "[clears throat]", "(laughs)". Short
# and digit-free in parentheses, so real speech in parentheses survives.
_SOUND_TAG = re.compile(r"\[[^\]]{0,60}\]|\([^()\d]{1,40}\)")


def strip_sound_tags(text: str) -> str:
    return _SOUND_TAG.sub(" ", text)


def clean_transcript(text: str) -> str:
    """The words only, as the agent and the transcript should see them:
    "হ্যাঁ, আমি কালকে আসছি। [গলা ঝারার শব্দ]" -> "হ্যাঁ, আমি কালকে আসছি।"."""
    return " ".join(strip_sound_tags(text).split())


def is_sound_only(text: str) -> bool:
    """Only non-speech tags ("[clears throat]"): nobody said anything."""
    return bool(_SOUND_TAG.search(text)) and not words(text)


def words(text: str) -> list[str]:
    text = strip_sound_tags(text)
    return [t for t in _SPLIT.split(text.strip().lower()) if any(c.isalpha() for c in t)]


def normalize(text: str) -> str:
    return " ".join(words(text))


def _is_bengali(c: str) -> bool:
    return "ঀ" <= c <= "৿"


def _is_latin(c: str) -> bool:
    return c.isascii() or "À" <= c <= "ɏ"


# Letters in another script that make a turn another language even when
# English words outnumber them: "आ वो लोग milestone repeat की" (run_53).
_OTHER_SCRIPT_MIN_LETTERS = 3

# A phone number (seven or more digits, spaces and dashes allowed) or an email.
_PHONE_OR_CONTACT_RE = re.compile(r"\+?\d(?:[\s-]?\d){6,}|\S+@\S+\.\w+")


def classify_script(text: str) -> Script:
    """The script most of the letters are in. Voice STT writes Bangla in Bengali
    script and English in Latin; anything else (Devanagari, Arabic, Cyrillic) is
    another language -- also when a few of its letters sit among English words,
    since a Bangla or English speaker's turn has none."""
    bn = en = other = 0
    for c in text:
        if not c.isalpha():
            continue
        if _is_bengali(c):
            bn += 1
        elif _is_latin(c):
            en += 1
        else:
            other += 1
    if bn + en + other == 0:
        return "none"
    if other > bn + en or (other >= _OTHER_SCRIPT_MIN_LETTERS and other > bn):
        return "other"
    # Any Bengali letters: Bangla with English loanwords, which can have more
    # Latin letters than Bengali ones ("জি, data pack টা confirm করুন।"). English
    # speakers never write Bengali script.
    if bn > 0:
        return "bn"
    return "en"


def has_contact(text: str) -> bool:
    """A phone number or an email: never filler, whatever its script."""
    return bool(_PHONE_OR_CONTACT_RE.search(text))


def is_filler_or_empty(text: str) -> bool:
    if has_contact(text):
        return False
    ws = words(text)
    return not ws or all(w in _FILLERS for w in ws)


def is_assent_filler(text: str) -> bool:
    ws = words(text)
    return bool(ws) and all(w in _ASSENT_FILLERS for w in ws)


_CLOSING_WORDS = [words(phrase) for phrase in _CLOSING_PHRASES]


def is_closing(text: str) -> bool:
    """A short turn that says goodbye, thanks or that they need nothing more."""
    ws = words(text)
    if not ws or len(ws) > _CLOSING_MAX_WORDS:
        return False
    return any(
        ws[i : i + len(phrase)] == phrase
        for phrase in _CLOSING_WORDS
        for i in range(len(ws) - len(phrase) + 1)
    )


def is_stop_phrase(text: str) -> bool:
    norm = normalize(text)
    return any(norm == p or norm.startswith(p + " ") for p in _STOP_PHRASES)


def is_bare_stop_phrase(text: str) -> bool:
    """Nothing but a stop phrase ("Wait.", "না না।")."""
    return normalize(text) in _STOP_PHRASES


def _words_without_digits(text: str) -> list[str]:
    return [w for w in words(text) if not any(c.isdigit() for c in w)]


def is_echo(text: str, bot_texts: list[str], min_ratio: float = 0.6) -> bool:
    """True if the transcript is mostly the agent's own recent speech picked up
    by the mic, compared word by word in order. Digits are dropped from both
    sides: the agent's text keeps "85" while the TTS said "eighty-five"."""
    heard = _words_without_digits(text)
    if len(heard) < 2:
        return False
    for bot in bot_texts:
        said = _words_without_digits(bot)
        if not said:
            continue
        blocks = difflib.SequenceMatcher(None, heard, said, autojunk=False).get_matching_blocks()
        if sum(b.size for b in blocks) / len(heard) >= min_ratio:
            return True
    return False


def address_form(text: str) -> str | None:
    """"formal", "informal", or None when the Bangla text shows neither (or both)."""
    formal = informal = False
    for word in words(text):
        if word in _FORMAL_WORDS or word.endswith(_FORMAL_ENDINGS):
            formal = True
        if word in _INFORMAL_WORDS or word.endswith(_INFORMAL_ENDINGS):
            informal = True
    if formal == informal:
        return None
    return "formal" if formal else "informal"


def confidence_known(confidence: float | None) -> bool:
    """OpenRouter's STT reports no confidence, which arrives as 0.0."""
    return confidence is not None and confidence > 0.0


def matches_handled(text: str, handled: str | None, age_s: float, window_s: float = 10.0) -> bool:
    """Whether a committed turn is the same speech a barge-in already answered.
    The library joins its own finals, so compare by containment, not equality."""
    if not handled or age_s > window_s:
        return False
    a, b = normalize(text), normalize(handled)
    return bool(a) and bool(b) and (a in b or b in a)


class Verdict(StrEnum):
    DROP = "drop_silent"
    OTHER_LANGUAGE = "say_other_language"
    ACCEPT = "accept"


@dataclass(frozen=True)
class Thresholds:
    drop_p: float = 0.35
    min_confidence: float = 0.4
    other_language_min_words: int = 3
    other_language_cooldown_s: float = 180.0


@dataclass
class GateState:
    """When the other-language line was said, so it doesn't repeat."""

    other_language_at: float | None = None
    other_language_since_reply: bool = False

    def record(self, verdict: Verdict, now: float) -> None:
        if verdict is Verdict.OTHER_LANGUAGE:
            self.other_language_at = now
            self.other_language_since_reply = True
        elif verdict is Verdict.ACCEPT:
            self.other_language_since_reply = False


_PRESENCE_CHECK_RE = re.compile(
    r"শুনতে\s*পাচ্ছ|শুনতে\s*পাচ্ছেন|শোনা\s*যাচ্ছে|কথা\s*শোনা|কথা\s*কি\s*শুনতে|hello\??$|can\s*you\s*hear|are\s*you\s*there",
    re.I,
)


def is_presence_check(text: str) -> bool:
    return bool(_PRESENCE_CHECK_RE.search(text))


@dataclass(frozen=True)
class Precheck:
    script: Script
    filler: bool
    assent: bool
    word_count: int
    confidence: float | None
    closing: bool = False
    presence: bool = False


def precheck(text: str, confidence: float | None) -> Precheck:
    contact = has_contact(text)
    script = classify_script(strip_sound_tags(text))
    if script == "none" and contact:
        script = "bn"
    return Precheck(
        script=script,
        filler=is_filler_or_empty(text),
        assent=is_assent_filler(text),
        word_count=max(len(words(text)), 1 if contact else 0),
        confidence=confidence if confidence_known(confidence) else None,
        closing=is_closing(text),
        presence=is_presence_check(text),
    )


def needs_judge(pre: Precheck, *, stt_writes_bengali: bool) -> bool:
    """False when the pre-checks alone settle the turn."""
    if pre.filler or pre.closing or pre.script == "none":
        return False
    return not (pre.script == "other" and stt_writes_bengali)


def decide(
    pre: Precheck,
    p: float | None,
    *,
    stt_writes_bengali: bool,
    state: GateState,
    now: float,
    th: Thresholds = Thresholds(),
    bot_asked: bool = False,
) -> Verdict:
    """The turn's fate, from the pre-checks and the judge's P(addressed).

    Below drop_p the turn is ignored silently: bystanders, TV and off-topic
    requests never reach the LLM. p is None when the judge wasn't asked or
    failed: accept, since ignoring a real customer costs more than answering
    noise. `bot_asked`: the agent's last message was a question, so a bare
    "hmm" answers it."""
    if pre.filler and pre.assent and bot_asked:
        return Verdict.ACCEPT
    if pre.filler or pre.script == "none":
        return Verdict.DROP
    if pre.closing:
        return Verdict.ACCEPT
    if pre.presence:
        return Verdict.ACCEPT

    # Another script is only trusted as another language when the STT can write
    # Bangla at all; Deepgram renders Bangla speech in Latin or Devanagari.
    if pre.script == "other" and stt_writes_bengali:
        cooled = (
            state.other_language_at is None
            or now - state.other_language_at >= th.other_language_cooldown_s
        )
        confident = pre.confidence is None or pre.confidence >= th.min_confidence
        if (
            pre.word_count >= th.other_language_min_words
            and confident
            and cooled
            and not state.other_language_since_reply
        ):
            return Verdict.OTHER_LANGUAGE
        return Verdict.DROP

    if p is not None and p < th.drop_p:
        return Verdict.DROP
    return Verdict.ACCEPT
