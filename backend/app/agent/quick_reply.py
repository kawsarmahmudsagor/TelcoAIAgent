"""Quick replies: a small, fast model makes a gated voice call feel quicker.

Jev already says which lookup each finished turn needs (turn_judge.LOOKUP_KEY).
That one answer picks the path (route):

- "fast": no lookup is needed (a greeting, thanks, a question about what was
  already said), so the small model answers the turn itself. It sees the whole
  conversation and the same instructions, plus FAST_RULES, and has no tools but
  end_call. When the turn needs anything it can't answer from the conversation
  it writes HANDOFF and nothing else, and the main model answers instead
  (stream_fast hands off without a word of it spoken).
- "filler": a lookup or an account tool is needed, so one short line ("let me
  check that") is spoken until the main model's reply starts: while the lookup
  runs, and after it in front of the reply if the line is ready before the
  reply's first words, else dropped. With quick_filler_llm on (the default)
  the small model writes the line for the turn, as a care agent would say it
  (compose_filler with _CARE_FILLER_SYSTEM); a line it doesn't write in time
  is no line. Off, the line comes from fast_filler's templates in under a
  millisecond (and its audio from app.agent.audio_cache once said before),
  picked by what the turn is about: Jev's topic answer when it is sure
  (judged_topic), else the customer's words; only a turn they don't fit asks
  the small model. Either way the line states no facts: safe_filler drops one
  with numbers, money or contact details the customer didn't say.
- "guest": a guest asks about their own account, which needs a login: a
  fixed line (guest_line) answers at once, with no model. A guest's account
  ask the guest route isn't sure of gets no filler: it goes "fast", where
  FAST_GUEST_RULES has the small model give the login line itself.

Anything less sure stays on the main model, as without quick replies.
"""

import asyncio
import json
import logging
import random
import re
import time
import unicodedata
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal

import httpx
from livekit.agents import APIConnectOptions, llm
from livekit.agents.voice.generation import INSTRUCTIONS_MESSAGE_ID

from app.agent import reply_language, turn_gate
from app.agent.audio_cache import AudioCache, normalize_text
from app.agent.quick_models import reasoning_for
from app.agent.turn_judge import Exchange, Judgement
from app.agent.reply_language import ReplyLanguage
from app.bss import care_centres
from app.config import Settings
from app.services.agent_config_service import ResolvedAgentConfig

logger = logging.getLogger("agent.quick_reply")
usage_logger = logging.getLogger("agent.usage")

Route = Literal["fast", "filler", "guest"]

# The small model's way of saying "the main model should answer this".
HANDOFF = "[[MAIN]]"

FILLER_MAX_WORDS = 12
# A line the small model writes for every turn may say a little more.
CARE_FILLER_MAX_WORDS = 15
# How many earlier lines the filler is told not to repeat.
_AVOID = 5

_NUMBER_RE = re.compile(r"\d+")  # Bangla digits too
_MONEY_RE = re.compile(r"৳|\$|\btk\b|taka|টাকা|\blakh|\bcrore|লাখ|লক্ষ|কোটি", re.IGNORECASE)
_HOW_MUCH_RE = re.compile(r"কত\s*টাকা|\bhow\s+much\s+(?:taka|money)\b", re.IGNORECASE)
# A phone number (seven or more digits, spaces and dashes allowed) or an email.
_CONTACT_RE = re.compile(r"\+?\d(?:[\s-]?\d){6,}|\S+@\S+\.\w+")

_FAST_LANGUAGE_LINE = (
    "Reply in the language of the customer's latest message (LANGUAGE above), whatever earlier "
    "turns used."
)
FAST_RULES = f"""

# Quick answer mode
You are answering this one turn quickly, from the conversation alone, with no tools except end_call.
{_FAST_LANGUAGE_LINE}
When the customer wraps up or says goodbye (also informally: tata, bye bye, আসি তাহলে, রাখি তাহলে,
ভালো থাকবেন), follow the instructions above for ending the call.
Answer only when everything you need was already said in this conversation or is in the instructions above:
greetings, thanks, small talk, goodbyes, or repeating or explaining something already said.
Reply with exactly {HANDOFF} and nothing else when the customer:
- asks for any balance, package, usage, price, offer, validity or policy fact not already said;
- asks again for their own balance, data, minutes, points or usage (it may have changed);
- wants to buy a package, recharge, redeem an offer or open a case, or gives a number to recharge;
- says a code of 4 to 8 digits (an OTP), in any language or script;
- complains about the network, a charge or the service;
- asks for a follow-up or a call back;
- asks anything you are not sure you can answer from the conversation.
Never guess a fact. When in doubt, reply with exactly {HANDOFF}."""

# Added to FAST_RULES for a guest (is_guest): their own account needs a login,
# so the small model answers that itself instead of handing off.
FAST_GUEST_RULES = f"""
The customer is not logged in (a guest; see ACCOUNT SNAPSHOT). When this turn only asks about
their own account (balance, data or minutes left, their package, transactions or deductions,
recharges, reward points, offers, support cases), or only asks to recharge, or to buy or redeem
something already named or shown, answer it yourself, without {HANDOFF}: say warmly that it needs
them logged in, that the Log in button is at the top of the page and that you'll do it straight
after, in one or two short sentences. You may offer one thing you can do now (find a package,
check the network, SIM or care centre questions). Never a bare "আগে লগইন করুন" or "please log in
first", and never say you are checking or looking it up. When a guest is upset or asks for a
person, answer yourself too: a short, sincere apology first, then politely offer our hotline (the
number in WHEN YOU DON'T HAVE A DETAIL), and that once they log in you can send our team a request
to follow up. When the turn also asks something else, or asks for a package by what they want
(data, price, validity), reply with exactly {HANDOFF}."""

# Added to the filler request for a guest: no line may promise an account check.
_FILLER_GUEST_NOTE = (
    "The customer is not logged in: their own balance, usage, package, transactions, "
    "recharges, points, offers and cases can't be checked. Never say you'll check any of those."
)

_FILLER_SYSTEM = """You write the short line a mobile operator's phone assistant says
while the main assistant handles the customer's request. The line is spoken aloud.

Write one short, warm, natural spoken sentence, preferably under 10 words.
Choose a style that fits the request and vary the sentence structure, not just individual words.

Styles to vary:
- Brief acknowledgement: "জি, বুঝেছি।"
- Understanding: "আপনার কথাটা বুঝতে পেরেছি।"
- Checking: "আচ্ছা, চেক করে আপনাকে জানাচ্ছি।"
- Polite request: "একটু সময় দেবেন, প্লিজ?"
- Empathy: "আপনার অসুবিধাটা বুঝতে পেরেছি।"
- Neutral response to a choice or follow-up: "আচ্ছা, ওটা নিয়ে বলছি।"

Language:
- Follow the language of the customer's newest message.
- For Bangla or Banglish, reply in natural spoken Bangla using Bengali script and respectful language.
- Use everyday words such as চেক, প্যাকেজ, ব্যালেন্স and ওকে.
- Say "দাম", not "প্রাইস".
- Say "প্যাকেজ", not "প্যাক".
- Avoid literary words such as মিলিয়ে, ঘেঁটে and খুলছি.
- Never a vague "বিষয়টা" or "ব্যাপারটা" ("বিষয়টা দেখছি"): name what you check, or leave it out.
- Keep familiar customer-care phrases such as "দেখে জানাচ্ছি", "দেখে বলছি",
  "আপনাকে জানাচ্ছি", and "আপনাকে বলছি" in the template pool.
- Use those update phrases when a lookup is actually happening or an answer is about to follow.
- Vary them with acknowledgements, empathy, and polite requests; do not remove them or use
  the same phrase in every reply.
- Do not repeat recent lines or their sentence structures.
- Avoid overly formal, robotic, or exaggeratedly apologetic language.

Safety:
- Never state a price, number, balance, availability, policy, or result that has not been verified.
- Only echo numbers or amounts the customer explicitly said.
- Never claim a recharge, payment, purchase, activation, complaint, or message has completed or succeeded.
- Never claim an operation has started or is being processed unless the current operation state explicitly confirms it.
- Never answer the customer's actual question; the main assistant will do that.
- Never promise an outcome or say a person is joining.
- Do not describe results as available, found, successful, or suitable before they have been checked.
- Do not imply that you are checking something unless a lookup or check is actually about to happen.
- No greeting, question, or emoji.

Return JSON only: {"text": "..."}"""

# For quick_filler_llm: the small model writes every filler line. Rules only, no
# example lines, so the lines don't drift toward a few fixed ones.
_CARE_FILLER_SYSTEM = f"""You are a mobile operator's care agent on a phone call. The customer's
request needs a lookup or an account action; another assistant gives the real answer next.
Say the one short spoken line a good care agent says first.

- React to what this customer said, naming what you'll check in their own terms (area,
  package size or validity, amount, balance). No stock phrases.
- Problem or complaint: a little empathy, then what you'll look into. Pick, correction or
  follow-up: a calm acknowledgement. Action (recharge, purchase): "I'll take care of it",
  never that it's done.
- Warm, natural, not robotic, over-apologetic or pushy. One sentence or two very short,
  max {CARE_FILLER_MAX_WORDS} words. Don't echo the shape of lines already said.

Language: match the customer's newest message. Bangla/Banglish: modern spoken Bangla,
Bengali script, আপনি. Use চেক, প্যাকেজ, ব্যালেন্স, রিচার্জ, অফার, নেটওয়ার্ক, কমপ্লেইন, সরি,
প্লিজ, ওকে. Say প্যাকেজ not প্যাক, দাম not প্রাইস, বুঝতে পেরেছি not বুঝতে পারছি, স্লো not ধীর.
No bookish words (মিলিয়ে, ঘেঁটে, খুলছি, অনুগ্রহপূর্বক), no slang, no vague বিষয়টা/ব্যাপারটা.
The operator is "telco", never "telco.".

Never: state a price, number, balance, validity, availability, policy or result; echo a
number the customer didn't say; say anything is done, started or successful; answer the
question; promise an outcome or a person joining; greet, ask, or use emoji.

Return JSON only: {{"text": "..."}}"""


@dataclass
class QuickReplyRuntime:
    """One session's quick-reply state: the config switches, the OpenRouter
    connection, and the filler lines said so far."""

    config: ResolvedAgentConfig
    settings: Settings
    api_key: str
    client: httpx.AsyncClient
    said: list[str] = field(default_factory=list)
    # Filler audio already synthesized: fast_filler prefers those lines.
    audio_cache: AudioCache | None = None
    # What the small model is doing, for the run log: "asked", "wrote ...", "timed out".
    on_event: Callable[[str], None] | None = None
    # The customer's picked reply language (app.agent.reply_language): every
    # filler is in it. None follows the language of their message.
    language: ReplyLanguage | None = None
    # Guest lines said so far (guest_line), so a second ask hears another.
    guest_said: list[str] = field(default_factory=list)
    _fast_llm: llm.LLM | None = None

    @property
    def fast_answer(self) -> bool:
        return self.config.quick_reply_enabled and self.config.quick_fast_answer

    @property
    def filler(self) -> bool:
        return self.config.quick_reply_enabled and self.config.quick_filler

    def fast_llm(self) -> llm.LLM:
        """Built on first use, so a call that never takes the fast path never
        opens its connection."""
        if self._fast_llm is None:
            self._fast_llm = build_fast_llm(self.config, self.settings, self.api_key)
        return self._fast_llm

    def guest_reply(self, topic: str, utterance: str) -> str:
        line = guest_line(
            topic, utterance, self.language, self.guest_said, self.config.operator_phone
        )
        self.guest_said.append(line)
        if self.on_event is not None:
            self.on_event(f'guest: fixed line for {topic} "{line}"')
        return line

    def avoid(self, utterance: str) -> list[str]:
        """The last lines said in the utterance's script (the picked language's,
        when there is one): a line in the other language would pull the new one
        toward it."""
        script = self.language or turn_gate.classify_script(utterance)
        return [line for line in self.said if turn_gate.classify_script(line) == script][-_AVOID:]

    async def compose(
        self,
        utterance: str,
        lookup: str | None,
        history: list[Exchange],
        *,
        topic: str | None = None,
        guest: bool = False,
    ) -> str | None:
        """topic: Jev's, when it is sure (judged_topic). guest: the customer
        isn't logged in, which the model-written line is told."""
        avoid = self.avoid(utterance)
        care = self.config.quick_filler_llm
        line = (
            None
            if care
            else fast_filler(
                utterance,
                lookup,
                history,
                avoid,
                cache=self.audio_cache,
                topic=topic,
                language=self.language,
            )
        )
        if line is not None:
            # One echoing the customer's words is new: its audio may be cached too.
            remember_filler(line)
            if self.on_event is not None:
                by = f" (Jev topic: {topic})" if topic else ""
                self.on_event(f'filler: template line "{line}"{by}')
            return line
        line = await compose_filler(
            self.client,
            self.settings.openrouter_base_url,
            self.api_key,
            self.config.quick_reply_model,
            utterance,
            lookup,
            history,
            avoid,
            timeout_s=self.settings.filler_timeout_ms / 1000,
            on_event=self.on_event,
            topic=topic,
            care=care,
            language=self.language,
            guest=guest,
        )
        if line is not None:
            remember_filler(line)
        return line


# ---- template fillers ----
#
# Lines in the way the small model is told to write them (_FILLER_SYSTEM):
# everyday spoken Bangla with the English words people use (চেক, প্যাকেজ,
# ব্যালেন্স, ওকে), no literary words, no question, no number or price.
#
# Four kinds, as in the real-estate agent's fillers:
# - generic: checking, understanding, affirming; never wrong, never specific;
# - echo: "{x} চেক করে বলছি" with x what the customer asked about, as their topic
#   ("আপনার ব্যালেন্সটা") or in their own words ("মিরপুর এলাকার নেটওয়ার্কটা",
#   "সাত দিনের ডাটা প্যাকেজগুলো");
# - topic: a few hand-written lines per topic that the echo shape can't say;
# - intent: a correction ("না, মিনিট চাচ্ছিলাম") or a pick from a shown list
#   ("দ্বিতীয়টা").


def _re(pattern: str) -> re.Pattern[str]:
    # Utterances are NFC (which splits a precomposed য়), so patterns are too.
    return re.compile(unicodedata.normalize("NFC", pattern), re.I)


_CHECKING_BN = (
    "একটু সময় দেবেন, প্লিজ।",
    "আচ্ছা, এক মিনিট সময় দিন।",
    "জি, আমাকে একটু সময় দিন।",
    "চেক করে জানাচ্ছি, একটু অপেক্ষা করুন।",
    "দেখে আপনাকে বলছি, এক মিনিট।",
    "জি, দেখে আপনাকে জানাচ্ছি।",
    "জি, চেক করে বলছি।",
    "আচ্ছা, এখনই দেখে বলছি।",
    "জি, এখনই জানিয়ে দিচ্ছি।",
    "জি, অবশ্যই। চেক করে জানাচ্ছি।",
)
_UNDERSTANDING_BN = (
    "জি, বুঝতে পেরেছি। একটু সময় দিন।",
    "বুঝতে পেরেছি। দেখে আপনাকে জানাচ্ছি।",
    "বুঝতে পেরেছি, দেখে বলছি, একটু সময় দিন।",
)
_GENERIC_BN = (*_CHECKING_BN, *_UNDERSTANDING_BN)

_CHECKING_EN = (
    "Sure, let me check that.",
    "One moment, please.",
    "Let me take a quick look.",
    "I'll check that for you.",
    "Please give me a moment.",
    "All right, let me look into it.",
    "Just a moment while I check.",
    "Let me take a closer look.",
    "Thanks, give me a moment.",
    "I'll have a look.",
)
_UNDERSTANDING_EN = (
    "I understand. Give me a moment.",
    "I see what you mean.",
    "Got it, let me look into that.",
    "I understand your concern.",
    "All right, I understand.",
    "I see what you're saying.",
    "Understood, just a moment.",
    "I understand what you need.",
    "Got it, one moment please.",
    "I follow you. Give me a moment.",
)
_GENERIC_EN = (*_CHECKING_EN, *_UNDERSTANDING_EN)

# x: what is being checked, with its article or classifier ("আপনার
# ব্যালেন্সটা", "the data packages"). Each topic takes the verbs of what is
# really being done: packages and places are searched for, the account is
# looked up, a status or a rule is checked. Every shape opens with its own
# word, and each says what comes next ("দেখে বলছি", "জানাচ্ছি"), never a
# bare দেখছি that sounds like the check is all there is.
_ECHO_BN: dict[str, tuple[str, ...]] = {
    "search": (
        "জি, আমি {x} চেক করে বলছি।",
        "আচ্ছা, বুঝেছি। {x} চেক করে জানাচ্ছি।",
        "{x} খুঁজে বলছি, এক সেকেন্ড।",
        "একটু সময় দিন, {x} খুঁজে আপনাকে জানাচ্ছি।",
        "এক সেকেন্ড, {x} এখনই দেখাচ্ছি।",
    ),
    "lookup": (
        "জি, {x} চেক করে আপনাকে জানাচ্ছি।",
        "আচ্ছা, {x} এখনই দেখে বলছি।",
        "অবশ্যই। {x} যাচাই করে আপনাকে জানাচ্ছি।",
        "{x} দেখে আপনাকে জানাচ্ছি, এক মিনিট।",
        "আমাকে একটু সময় দিন, {x} দেখে জানাচ্ছি।",
    ),
    "status": (
        "জি, {x} চেক করে আপনাকে জানাচ্ছি।",
        "এক সেকেন্ড, {x_of} স্ট্যাটাসটা যাচাই করে বলছি।",
        "আচ্ছা, {x_of} আপডেটটা দেখে জানাচ্ছি।",
        "{x_of} স্ট্যাটাসটা চেক করে বলছি, একটু সময় দিন।",
        "বুঝতে পেরেছি। {x} দেখে আপনাকে আপডেট দিচ্ছি।",
    ),
    # A care centre is looked for, in the area named: "মিরপুর এলাকার কেয়ার
    # সেন্টার খুঁজে বলছি". x_cc says it as কাস্টমার কেয়ার.
    "place": (
        "ওকে, {x} খুঁজে বলছি।",
        "এক মিনিট, {x_cc} খুঁজে আপনাকে জানাচ্ছি।",
        "আচ্ছা, {x_cc} খুঁজে আপনাকে বলছি।",
        "{x} খুঁজে জানাচ্ছি, একটু সময় দিন।",
        "জি, অবশ্যই। {x} খুঁজে আপনাকে জানাচ্ছি।",
    ),
    # A complaint or a rule has no status: "সমস্যাটার স্ট্যাটাস" is wrong.
    "issue": (
        "জি, {x} চেক করে আপনাকে জানাচ্ছি।",
        "আচ্ছা, বুঝতে পেরেছি। {x} দেখে আপনাকে বলছি।",
        "ঠিক আছে, {x} খোঁজ নিয়ে জানাচ্ছি।",
        "{x} দেখে বলছি, একটু সময় দিন।",
        "আমাকে একটু সময় দিন, {x} দেখে বলছি।",
    ),
}

_ECHO_EN: dict[str, tuple[str, ...]] = {
    "search": (
        "Sure, finding {x}.",
        "Okay, looking up {x} now.",
        "Got it, let me check {x}.",
        "Alright, pulling up {x}.",
        "One moment, I'll find {x}.",
    ),
    "lookup": (
        "Sure, checking {x}.",
        "Okay, pulling up {x} now.",
        "Got it, let me look at {x}.",
        "Alright, getting {x}.",
        "One moment, I'll check {x}.",
    ),
    "status": (
        "Sure, checking {x}.",
        "Okay, looking into {x} now.",
        "Got it, let me check on {x}.",
        "Alright, I'll look into {x}.",
        "One moment, I'll find out about {x}.",
    ),
}
_ECHO_EN["issue"] = _ECHO_EN["status"]
_ECHO_EN["place"] = _ECHO_EN["search"]

# What each topic checks, for the echo lines: (Bangla, English, verb family).
_TOPIC_X: dict[str, tuple[str, str, str]] = {
    "data": ("ডাটা প্যাকেজগুলো", "the data packages", "search"),
    "voice": ("মিনিট প্যাকেজগুলো", "the minute packages", "search"),
    "bundle": ("কম্বো প্যাকেজগুলো", "the combo packages", "search"),
    "sms": ("এসএমএস প্যাকেজগুলো", "the SMS packages", "search"),
    "pack": ("প্যাকেজগুলো", "the packages", "search"),
    "offer": ("আপনার অফারগুলো", "your offers", "search"),
    "care": ("কাছের কেয়ার সেন্টার", "the nearest care centre", "place"),
    "balance": ("আপনার ব্যালেন্সটা", "your balance", "lookup"),
    "usage": ("আপনার ইউসেজটা", "your usage", "lookup"),
    "points": ("আপনার পয়েন্টগুলো", "your points", "lookup"),
    "transactions": ("ট্রানজেকশনগুলো", "your recent transactions", "lookup"),
    "recharge": ("রিচার্জটা", "your recharge", "status"),
    "network": ("আপনার এলাকার নেটওয়ার্কটা", "the network in your area", "status"),
    "complaint": ("সমস্যাটা", "the issue", "issue"),
    "policy": ("তথ্যটা", "the details", "issue"),
}

_TOPIC_EXTRA_BN: dict[str, tuple[str, ...]] = {
    "data": ("আপনার জন্য কী কী ডাটা প্যাকেজ আছে, দেখে জানাচ্ছি।",),
    "voice": ("কোন কোন মিনিট প্যাকেজ আছে, দেখে বলছি, একটু সময় দিন।",),
    "bundle": ("জি, ডাটা আর মিনিট একসাথে কী আছে, চেক করে বলছি।",),
    "sms": ("কোন কোন এসএমএস প্যাকেজ আছে, চেক করে বলছি, এক মিনিট।",),
    "pack": ("জি, আপনার জন্য কোন প্যাকেজগুলো আছে, চেক করে জানাচ্ছি।",),
    "balance": ("জি, অবশ্যই। ব্যালেন্সটা দেখে আপনাকে বলছি।",),
    "usage": ("কতটুকু ইউজ হয়েছে, চেক করে আপনাকে জানাচ্ছি।",),
    "recharge": ("রিচার্জটা ঠিকমতো হয়েছে কি না, দেখে জানাচ্ছি।",),
    "offer": ("আপনার নম্বরে কী কী অফার আছে, দেখে বলছি, এক মিনিট।",),
    "points": ("কত পয়েন্ট জমেছে, চেক করে আপনাকে জানাচ্ছি।",),
    "transactions": ("বুঝতে পেরেছি। ব্যালেন্স কেন কেটেছে, চেক করে আপনাকে বলছি।",),
    "network": ("আপনার এলাকায় নেটওয়ার্ক কেমন, দেখে জানাচ্ছি।",),
    "care": ("এক সেকেন্ড, আপনার কাছের কাস্টমার কেয়ার খুঁজে আপনাকে জানাচ্ছি।",),
    "complaint": ("সরি, অসুবিধার জন্য। সমস্যাটা চেক করে আপনাকে জানাচ্ছি।", "বুঝতে পেরেছি, কী করা যায় দেখে বলছি।"),
    "policy": ("আচ্ছা, নিয়মটা দেখে আপনাকে জানাচ্ছি।",),
}
_TOPIC_EXTRA_EN: dict[str, tuple[str, ...]] = {
    "data": ("Let's see which data packages suit you.",),
    "voice": ("Let's see which minute packages suit you.",),
    "bundle": ("Let's see which data and minute bundles we have.",),
    "sms": ("Let's see which SMS packages we have.",),
    "pack": ("Let's see which packages suit you.",),
    "balance": ("Let me pull up your current balance.",),
    "usage": ("I'll check how much you've used so far.",),
    "recharge": ("Let me see if your recharge went through.",),
    "offer": ("Let's see what offers your number has.",),
    "points": ("I'll check how many points you've earned.",),
    "transactions": ("I'll check where the deduction came from.",),
    "network": ("I'll see if there's a network issue near you.",),
    "care": ("Let me find the care centre closest to you.",),
    "complaint": ("Sorry about that, I'll look into it.",),
    "policy": ("Okay, I'll check the rule on that.",),
}

# A topic's kinds of question, each with its own lines: "রিচার্জ আসেনি" is
# about one recharge, "সর্বনিম্ন কত রিচার্জ করা যায়?" about the rule. The
# first kind whose words the customer used wins; none, the topic's default.
_RECHARGE_STATUS_BN = (
    "আচ্ছা, রিচার্জের স্ট্যাটাসটা দেখে আপনাকে আপডেট দিচ্ছি।",
    "জি, আপনার রিচার্জটা হয়েছে কি না, চেক করে বলছি।",
    "রিচার্জটা ব্যালেন্সে যোগ হয়েছে কি না দেখে বলছি, একটু সময় দিন।",
    "বুঝতে পেরেছি। রিচার্জের স্ট্যাটাসটা চেক করে জানাচ্ছি।",
    "জি, আমাকে একটু সময় দিন, রিচার্জটা যাচাই করে বলছি।",
    "রিচার্জের আপডেটটা দেখে আপনাকে জানাচ্ছি, এক মিনিট।",
    "সরি, অসুবিধার জন্য। রিচার্জের তথ্যটা যাচাই করে জানাচ্ছি।",
)
_RECHARGE_STATUS_EN = (
    "Let me check the recharge status.",
    "I'll look into whether the recharge went through.",
    "I understand your concern about the recharge.",
    "One moment while I check the recharge status.",
    "Let me take a look at the recharge update.",
)
_RECHARGE_LIMIT_BN = (
    "জি, রিচার্জের লিমিট যাচাই করে আপনাকে জানাচ্ছি।",
    "রিচার্জের লিমিটটা দেখে আপনাকে বলছি, এক মিনিট।",
    "আচ্ছা, রিচার্জের লিমিটটা এখনই জানিয়ে দিচ্ছি।",
    "জি, বুঝেছি। রিচার্জ লিমিটটা চেক করে বলছি।",
)
_RECHARGE_LIMIT_EN = (
    "Let me check the recharge limit.",
    "I understand your question about the recharge limit.",
    "One moment while I look into the limit.",
    "Got it, regarding the recharge limit.",
)
_RECHARGE_HOW_BN = (
    "আচ্ছা, কীভাবে রিচার্জ করবেন, সেটা একটু বুঝিয়ে বলছি।",
    "জি, অবশ্যই। রিচার্জ করার নিয়মটা আপনাকে বলছি।",
    "ঠিক আছে, রিচার্জের উপায়গুলো এখনই বলছি।",
    "জি, রিচার্জ করার ধাপগুলো আপনাকে জানাচ্ছি, একটু সময় দিন।",
)
_RECHARGE_HOW_EN = (
    "I understand your question about recharging.",
    "Let me look into the recharge steps.",
    "Got it, regarding how to recharge.",
    "One moment while I check the recharge process.",
)
_RECHARGE_PERKS_BN = (
    "এখন কী কী রিচার্জ অফার আছে, দেখে আপনাকে বলছি।",
    "রিচার্জের সুবিধাগুলো দেখে জানাচ্ছি, এক মিনিট।",
    "জি, রিচার্জে কী কী সুবিধা পাবেন, চেক করে বলছি।",
    "আচ্ছা, রিচার্জের অফারগুলো একটু যাচাই করে আপনাকে জানাচ্ছি।",
    "জি, অবশ্যই। রিচার্জের অফারগুলো চেক করে বলছি।",
)
_RECHARGE_PERKS_EN = (
    "I understand your question about recharge offers.",
    "Let me look into the recharge offers.",
    "Got it, regarding the available offers.",
    "One moment while I check the offers.",
)
# topic -> ((kind, its words, Bangla lines, English lines), ...), first match
# wins. Perks before limits before how-to: "বিকাশে রিচার্জ করলে ক্যাশব্যাক
# কত?" is about the cashback. A question of no kind gets a generic line: a
# guessed kind ("রিচার্জটা ঠিকমতো হয়েছে কি না") is worse than none.
_KINDS: dict[str, tuple[tuple[str, re.Pattern[str], tuple[str, ...], tuple[str, ...]], ...]] = {}
# Topics whose own lines fit a question of no kind: "পয়েন্টগুলো কি জমা
# হয়েছে?" is about how many there are.
_PLAIN_FITS = {"points"}

# "reward point কিভাবে accumulate করা যায়?" asks how points are earned, not
# how many there are; "পয়েন্ট দিয়ে কী নিতে পারি?" what they buy.
_POINTS_EARN_BN = (
    "ঠিক আছে, কীভাবে পয়েন্ট পাবেন, সেটা বলছি।",
    "পয়েন্ট পাওয়ার উপায়গুলো দেখে বলছি, একটু সময় দিন।",
    "জি, পয়েন্ট কীভাবে অ্যাড হয়, দেখে জানাচ্ছি।",
    "আচ্ছা, বুঝেছি। পয়েন্ট জমানোর নিয়মটা জানাচ্ছি।",
)
_POINTS_EARN_EN = (
    "Let me check how you can earn points.",
    "Sure, I'll look into how points are earned.",
    "One moment, checking the points rules.",
    "Okay, let me see how points add up.",
)
_POINTS_REDEEM_BN = (
    "একটু সময় দিন, রিওয়ার্ডগুলো দেখে আপনাকে বলছি।",
    "আচ্ছা, পয়েন্ট রিডিমের অপশনগুলো আপনাকে দিচ্ছি।",
    "জি, পয়েন্ট দিয়ে কী কী নিতে পারবেন, দেখে বলছি।",
    "পয়েন্ট কীভাবে ব্যবহার করবেন, দেখে বলছি, এক সেকেন্ড।",
)
_POINTS_REDEEM_EN = (
    "Let me check what your points can get you.",
    "Sure, I'll look at the redeem options.",
    "One moment, checking the rewards.",
    "Okay, let me see how you can use your points.",
)

_CORRECTION_BN = (
    "আচ্ছা, বুঝেছি।",
    "জি, আপনি কী বোঝাতে চাচ্ছেন বুঝতে পেরেছি।",
    "ঠিক আছে, এবার বুঝতে পেরেছি।",
)
_CORRECTION_EN = (
    "All right, understood.",
    "Got it, thanks for clarifying.",
    "Okay, I see what you mean now.",
    "Understood, let me adjust that.",
    "Thanks for clearing that up.",
)
_CHOICE_BN = (
    "ঠিক আছে, তাহলে এই প্যাকেজটার বিস্তারিত আপনাকে জানাচ্ছি।",
    "জি, বুঝেছি। ওই প্যাকেজটার বিস্তারিত বলছি।",
    "এই প্যাকেজটার তথ্য দেখে জানাচ্ছি, এক মিনিট।",
)
_CHOICE_EN = (
    "All right, that one.",
    "Sure, let's go with that one.",
    "Got it, you mean that option.",
    "Okay, that option it is.",
)

# A follow-up on what the last filler already named: a person says "এটাও
# দেখে বলছি", not "তিন জিবির ডাটা প্যাকেজগুলো দেখে বলছি" turn after turn.
_FOLLOW_UP_BN = (
    "জি, আরও বলছি।",
    "ঠিক আছে, বিস্তারিত বলছি।",
    "আচ্ছা, আরও তথ্য দিচ্ছি।",
    "অবশ্যই, আপনাকে বিস্তারিত জানাচ্ছি।",
)
_FOLLOW_UP_EN = (
    "Sure, I'll explain a bit more.",
    "Let me add some detail.",
    "Of course, here's a little more.",
    "All right, I'll elaborate.",
    "Let me clarify that a little.",
    "Sure, I'll go into more detail.",
)
# ... and when it names something new on the same topic ("চার জিবির?" after
# "তিন জিবির"): x with "also".
_FOLLOW_UP_ECHO_BN = (
    "জি, {x}ও দেখে বলছি।",
    "আচ্ছা, {x}ও চেক করে জানাচ্ছি।",
    "ঠিক আছে, এবার {x} দেখে বলছি।",
    "{x}ও দেখে জানাচ্ছি, এক সেকেন্ড।",
)
_FOLLOW_UP_ECHO_EN = (
    "Sure, I'll check {x} too.",
    "Let me look at {x} as well.",
    "All right, checking {x} now.",
    "Okay, I'll look for {x} too.",
)
# "আরও কিছু options দেখান", "এগুলো ছাড়া আর কী আছে?"
_MORE_BN = (
    "ঠিক আছে, অন্য অপশনগুলো আপনাকে দিচ্ছি।",
    "জি, অন্য বিকল্পগুলো দেখে জানাচ্ছি।",
    "আরও কিছু অপশন দেখে জানাচ্ছি, এক মিনিট।",
    "আচ্ছা, অন্য বিকল্পগুলোও একটু দেখে বলছি।",
    "জি, অবশ্যই। আর কী কী অপশন আছে, দেখে বলছি।",
    "এক সেকেন্ড, আরও কিছু বিকল্প চেক করে জানাচ্ছি।",
    "এগুলো ছাড়া আর কী আছে, এখনই দেখাচ্ছি।",
)
_MORE_EN = (
    "Sure, let's look at more options.",
    "I'll check what else is available.",
    "All right, let me check for other options.",
    "Let me look at the alternatives.",
    "Sure, I'll look for other options.",
)
# "এই প্যাকেজটা নিতে চাচ্ছি", "আগে রিচার্জ করুন": no outcome promised, the
# code or a shortfall may come next.
_ACTION_BN = (
    "জি, ঠিক আছে।",
    "ঠিক আছে, একটু সময় দিন।",
    "জি, এক মুহূর্ত সময় দিন।",
    "জি, অবশ্যই।",
    "আচ্ছা, ঠিক আছে।",
    "আচ্ছা, বুঝতে পেরেছি।",
)
_ACTION_EN = (
    "Sure, understood.",
    "All right, I understand.",
    "Got it, one moment.",
    "Okay, I understand your request.",
    "Sure, that's clear.",
    "Understood, give me a moment.",
    "All right, noted.",
    "Okay, I follow.",
    "Certainly, understood.",
    "Got it.",
    "All right.",
    "Absolutely.",
    "Okay, understood.",
    "Sure, no problem.",
    "All right, I follow.",
    "Understood, thanks.",
    "Okay, I hear you.",
    "Certainly.",
)


_KINDS["recharge"] = (
    ("perks", _re(r"ক্যাশব্যাক|বোনাস|পয়েন্ট|\bcash\s*back\b|\bbonus\b|\bpoints?\b"),
     _RECHARGE_PERKS_BN, _RECHARGE_PERKS_EN),
    ("limit", _re(r"সর্বনিম্ন|সর্বোচ্চ|কত\s*পর্যন্ত|লিমিট|কম\s*করে|"
                  r"\bminimum\b|\bmaximum\b|\blimits?\b|\bat\s+least\b"),
     _RECHARGE_LIMIT_BN, _RECHARGE_LIMIT_EN),
    ("how", _re(r"কিভাবে|কীভাবে|কি\s*ভাবে|কোথা\s*থেকে|বিকাশ|নগদ|কার্ড|প্রসেস|পদ্ধতি|"
                r"উপায়|নিয়ম|সিস্টেম|\bhow\b|\bbkash\b|\bnagad\b|\bcard\b|\bprocess\b|"
                r"\bsteps?\b|\bways?\b|\bmethods?\b"),
     _RECHARGE_HOW_BN, _RECHARGE_HOW_EN),
    # Only when something went wrong with one: "আসেনি", "টাকা কেটে গেছে".
    ("status", _re(r"আসেনি|আসে\s*নাই|আসছে\s*না|হয়নি|হয়\s*নি|হয়\s*নাই|হচ্ছে\s*না|"
                   r"পাইনি|পাই\s*নাই|পাচ্ছি\s*না|ঢোকেনি|কেটে|কাটা|ফেইল|ব্যর্থ|পেন্ডিং|আটকে|"
                   r"\bfailed\b|\bpending\b|\bstuck\b|\bdeducted\b|\bnot\s+(?:received|credited)\b|"
                   r"\bdid(?:n'?t|\s+not)\s+(?:get|go|come|arrive|receive)\b"),
     _RECHARGE_STATUS_BN, _RECHARGE_STATUS_EN),
)
# Redeem before earn: "কিভাবে রিডিম করব?" is about redeeming.
_KINDS["points"] = (
    ("redeem", _re(r"রিডিম|ব্যবহার|খরচ|দিয়ে\s*(?:কী|কি)|\bredeem\w*|\buse\b|\bspend\b"),
     _POINTS_REDEEM_BN, _POINTS_REDEEM_EN),
    ("earn", _re(r"কিভাবে|কীভাবে|কি\s*ভাবে|জমা(?:নো|তে|ব|বো|য়)|জমে|পাওয়া\s*যায়|"
                 r"পাব|পাবো|উপায়|নিয়ম|\bearn\w*|\baccumulat\w*|\bcollect\w*|"
                 r"\bhow\s+(?:do|can|to)\b"),
     _POINTS_EARN_BN, _POINTS_EARN_EN),
)


def _kind(topic: str | None, utterance: str) -> tuple[str, tuple[str, ...], tuple[str, ...]] | None:
    """(kind, Bangla lines, English lines) for the kind of question this is
    about the topic, or None: a topic without kinds, or no kind's words."""
    for name, pattern, bn, en in _KINDS.get(topic or "", ()):
        if pattern.search(utterance):
            return name, bn, en
    return None


def _line_kind(line: str) -> str | None:
    """The kind whose lines include this filler, or None."""
    for rows in _KINDS.values():
        for name, _pattern, bn, en in rows:
            if line in bn or line in en:
                return name
    return None


def _echo(templates: tuple[str, ...], x: str) -> tuple[str, ...]:
    """The shapes about x. "আপনার ব্যালেন্সটা চেক করে আপনাকে জানাচ্ছি" says
    আপনি twice: with x already "আপনার …", the আপনাকে goes."""
    if "আপনার" in x:
        templates = tuple(t.replace(" আপনাকে ", " ") for t in templates)
    cc = x.replace("কেয়ার সেন্টার", "কাস্টমার কেয়ার")
    return tuple(t.format(x=x, x_of=_of(x), x_cc=cc) for t in templates)


def _of(x: str) -> str:
    """x's possessive for {x_of}: "রিচার্জটা" -> "রিচার্জের", not "রিচার্জটা এর"."""
    return f"{x[:-2]}ের" if x.endswith("টা") else f"{x}র"


def _echo_lines(topic: str, x: str, bangla: bool) -> tuple[str, ...]:
    """The echo shapes of the topic's verb family, about x."""
    family = _TOPIC_X[topic][2]
    return _echo((_ECHO_BN if bangla else _ECHO_EN)[family], x)


def _topic_lines(topic: str, bangla: bool) -> tuple[str, ...]:
    x_bn, x_en, _ = _TOPIC_X[topic]
    if bangla:
        return (*_echo_lines(topic, x_bn, True), *_TOPIC_EXTRA_BN.get(topic, ()))
    return (*_echo_lines(topic, x_en, False), *_TOPIC_EXTRA_EN.get(topic, ()))


# Word lists shared by the topics below, so each topic knows the same words.
# Bangla is matched in the decomposed য় (য + nukta) that NFC gives.
_PACK = r"(?:প্যাক|প্যাকেজ|\bpacks?\b|\bpackages?\b)"
_DATA = r"(?:ডাটা|ডেটা|ইন্টারনেট|নেট|জিবি|এমবি|\bdata\b|\binternet\b|\bgb\b|\bmb\b)"
_MINUTES = r"(?:মিনিট|টকটাইম|\bminutes?\b|\bvoice\b|\btalk\s*time\b)"
# "How much is left": asks about the customer's own pack, not packs to buy.
_LEFT = r"(?:বাকি|কতটুকু|\bleft\b|\bremaining\b|\bbaki\b)"

# Ordered: the network before a care centre ("অফিসে নেট পাই না"), a dropped
# call before a money cut ("কেটে" means both), what is left before a pack
# kind, a pack kind before "pack", which is before what the pack is about. A
# turn no topic fits gets a generic line, which is never wrong.
_TOPIC_RES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("network", re.compile(
        r"নেটওয়ার্ক|সিগন্যাল|নেট\s*(?:নেই|নাই|পাই\s*না|পাচ্ছি\s*না|আসে\s*না|আসছে\s*না|স্লো)|(?:কল|লাইন).{0,15}(?:ড্রপ|কেটে)|"
        r"\bnetwork\b|\bsignal\b|\b(?:net|internet|data)\b.{0,15}\bslow\b|call\s*drop|"
        r"\bnetwork\s*nai\b", re.I)),
    ("care", _re(
        r"কেয়ার|সার্ভিস\s*সেন্টার|কাস্টমার\s*সেন্টার|অফিস|ব্রাঞ্চ|শোরুম|স্টোর|"
        r"\bcare\s*cent(?:re|er)s?\b|\bcustomer\s*care\b|\boffices?\b|\bbranch(?:es)?\b|"
        r"\bstores?\b|\bshowrooms?\b")),
    ("transactions", re.compile(
        r"লেনদেন|(?:টাকা|ব্যালেন্স).{0,15}(?:কেটে|কাট)|ডিডাক্ট|"
        r"\btransactions?\b|\bdeduct|\bcharged?\b|\b(?:taka|balance)\b.{0,15}\bkete\b",
        re.I)),
    ("bundle", re.compile(r"কম্বো|বান্ডেল|\bcombo\b|\bbundle\b", re.I)),
    ("sms", re.compile(r"এসএমএস|\bsms\b", re.I)),
    ("usage", re.compile(
        rf"(?:{_DATA}|{_MINUTES}).*{_LEFT}|{_LEFT}.*(?:{_DATA}|{_MINUTES})", re.I)),
    ("pack_data", re.compile(rf"{_DATA}.*{_PACK}|{_PACK}.*{_DATA}", re.I)),
    ("pack_voice", re.compile(rf"{_MINUTES}.*{_PACK}|{_PACK}.*{_MINUTES}", re.I)),
    ("pack", re.compile(_PACK, re.I)),
    ("balance", re.compile(r"ব্যালেন্স|\bbalance\b", re.I)),
    ("usage", re.compile(
        r"(?:ডাটা|ডেটা|ইন্টারনেট|মিনিট|\bdata\b|\bminutes?\b|\binternet\b).*"
        r"(?:বাকি|কতটুকু|কত|শেষ|\bleft\b|\bremaining\b|\bkoto\b|\bshesh\b)|"
        r"ইউসেজ|খরচ|\busage\b",
        re.I)),
    ("recharge", re.compile(r"রিচার্জ|টপ\s*আপ|\brecharge\b|\btop\s*up\b", re.I)),
    ("points", re.compile(r"পয়েন্ট|রিওয়ার্ড|রিডিম|\bpoints?\b|\brewards?\b|\bredeem\b", re.I)),
    ("offer", re.compile(r"অফার|\boffers?\b", re.I)),
    ("complaint", re.compile(r"অভিযোগ|সমস্যা|কমপ্লেইন|\bcomplain|\bproblem\b|\bissue\b", re.I)),
)
_PACK_KIND_TOPIC = {"pack_data": "data", "pack_voice": "voice"}

# A pack kind said on its own ("না, মিনিট চাচ্ছিলাম"): only after a correction.
_KIND_RES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("data", re.compile(_DATA, re.I)),
    ("voice", re.compile(_MINUTES, re.I)),
    ("sms", re.compile(r"এসএমএস|\bsms\b", re.I)),
    ("bundle", re.compile(r"কম্বো|বান্ডেল|\bcombo\b|\bbundle\b", re.I)),
)

# Bangla written in Latin letters: gets a Bangla line, as the small model is told.
_BANGLISH_RE = re.compile(
    r"\b(?:amar|apnar|ache|achhe|koto|koro|koren|dao|den|dekhao|dekhan|takar|moddhe|"
    r"kivabe|keno|chai|lagbe|ekta|holo|hobe|nai|kete|neya|jonno|er)\b",
    re.I,
)


def judged_topic(judgement: Judgement | None, settings: Settings) -> str | None:
    """The filler topic Jev gave the turn (turn_judge.TOPIC_KEY), or None when
    it wasn't asked, gave none ("other"), or isn't sure enough."""
    if judgement is None or judgement.topic not in _TOPIC_X:
        return None
    if judgement.topic_p is None or judgement.topic_p < settings.filler_topic_min_p:
        return None
    return judgement.topic


def _turn_topic(utterance: str, lookup: str | None, judged: str | None) -> str | None:
    """What the turn is about: Jev's topic, read in context, over the words'.
    Only "pack" yields to the words, when they name the package kind ("নেট
    প্যাক" is data)."""
    words = _filler_topic(utterance, lookup)
    if judged is None:
        return words
    if judged == "pack" and words in _PACK_TOPICS:
        return words
    return judged


def _filler_topic(utterance: str, lookup: str | None) -> str | None:
    # NFC splits a precomposed য় (U+09DF) the way the patterns spell it.
    utterance = unicodedata.normalize("NFC", utterance)
    for name, pattern in _TOPIC_RES:
        if pattern.search(utterance):
            return _PACK_KIND_TOPIC.get(name, name)
    if lookup == "packages":
        return "pack"
    if lookup == "knowledge_base":
        return "policy"
    return None


# ---- intents ----

# The customer takes back or corrects what they said: "না, ডাটা না, মিনিট
# চাচ্ছিলাম", "ডাটা প্যাক চাই না", "I didn't ask for that". A "না" that ends
# a complaint ("নেট পাচ্ছি না") is not one, nor is "নাকি" ("লাগবে নাকি
# ফটোকপি আনলেও হবে?" asks a question): each word ends where it ends.
_CORRECTION_RE = _re(
    r"^\s*(?:জি\s*)?(?:না|নাহ)(?=[\s,।!]|$)|"
    r"(?:চাইনি|চাই\s*নি|চাই\s*না|চাচ্ছি\s*না|চাচ্ছিলাম\s*না|বলিনি|বলি\s*নি|বলি\s*নাই|"
    r"লাগবে\s*না|দরকার\s*নেই|ভুল\s*বুঝেছেন)(?![ঀ-৿])|"
    r"^\s*(?:no|nope)\b|\bnot\s+that\b|\bdon'?t\s+want\b|"
    r"\bi\s+(?:didn'?t|did\s+not)\s+(?:ask|mean|want|say)\b"
)
# The last "না"/"not" in a correction: what comes after it is what they want.
_NEGATION_RE = _re(r"(?:^|[\s,।])(?:না|নয়|not|no)(?=[\s,।!?]|$)")

# A pick from a list the agent just showed: "দ্বিতীয়টা", "দুই নম্বরটা",
# "অন্যটা", "the second one", "the other one". Not "অন্য টাকা": no letter
# may follow টা beyond its own suffix.
_CHOICE_RE = _re(
    r"(?:প্রথম|দ্বিতীয়|তৃতীয়|চতুর্থ|পঞ্চম|শেষের|লাস্টের)\s*(?:টা|টি)|"
    r"(?:অন্য|পরের|আগের)\s*(?:টা|টি)(?:ই|ও|র|কে)?(?![ঀ-৿])|"
    r"(?:এক|দুই|তিন|চার|পাঁচ|[১-৫1-5])\s*নম্বর|ওই\s*প্যাক|"
    r"\b(?:first|second|third|fourth|fifth|last|other|next|previous)\s+"
    r"(?:one|option|pack|package|offer)\b|"
    r"\bthat\s+(?:one|pack|package|offer|option)\b"
)


def _corrected_topic(utterance: str) -> str | None:
    """What a correction asks for instead: the topic after its last "না", by
    the pack kind named last there, else any topic there."""
    tail = utterance
    for match in _NEGATION_RE.finditer(utterance):
        tail = utterance[match.end():]
    kinds = [
        (m.start(), kind) for kind, pattern in _KIND_RES for m in pattern.finditer(tail)
    ]
    if kinds:
        return max(kinds)[1]
    return _filler_topic(tail, None)


# ---- entities, echoed in the customer's words ----

# Places the care-centre finder knows (app.bss.care_centres), so a line only
# names a place the agent can act on. Longest first: "Old Dhaka" before "Dhaka".
def _places() -> list[tuple[re.Pattern[str], str, str]]:
    names: list[tuple[str, str, str]] = []  # (spelling, Bangla, English)
    for name, (bn, _centre, aliases) in care_centres.DISTRICTS.items():
        names += [(spelling, bn, name) for spelling in (name, bn, *aliases)]
    for name, (bn, _centre) in care_centres.DHAKA_AREAS.items():
        names += [(name, bn, name), (bn, bn, name)]
    names.sort(key=lambda n: len(n[0]), reverse=True)
    places = []
    for spelling, bn, en in names:
        spelling = unicodedata.normalize("NFC", spelling)
        # Bangla inflections attach directly ("মিরপুরে"); English is a whole word.
        pattern = re.escape(spelling) if not spelling.isascii() else rf"\b{re.escape(spelling)}\b"
        places.append((re.compile(pattern, re.I), bn, en))
    return places


_PLACES = _places()
# "মিরপুরে না, উত্তরায়": the place right before a "না" is not the one.
_PLACE_NEGATED_AFTER_RE = _re(r"^\S*\s+(?:না|নয়)(?=[\s,।!?]|$)")
_PLACE_NEGATED_BEFORE_RE = re.compile(r"\b(?:not|no)\s+(?:in\s+|at\s+)?$", re.I)


def _place(utterance: str) -> tuple[str, str] | None:
    """(Bangla, English) name of the last place the customer names and doesn't
    negate, or None."""
    found: list[tuple[int, int, str, str]] = []
    for pattern, bn, en in _PLACES:
        for m in pattern.finditer(utterance):
            # A shorter name inside a longer one already found ("Dhaka" in "Old Dhaka").
            if any(s <= m.start() and m.end() <= e for s, e, _, _ in found):
                continue
            found.append((m.start(), m.end(), bn, en))
    kept = [
        (start, bn, en)
        for start, end, bn, en in found
        if not _PLACE_NEGATED_AFTER_RE.search(utterance[end:end + 30])
        and not _PLACE_NEGATED_BEFORE_RE.search(utterance[max(0, start - 12):start])
    ]
    if not kept:
        return None
    _, bn, en = max(kept)
    return bn, en


# A pack's validity, as words: a line with a digit the customer didn't say
# would fail safe_filler, and words read the same either way.
_VALIDITY: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (_re(r"(?<![\d০-৯])(?:30|৩০|ত্রিশ|তিরিশ)\s*(?:দিন|days?\b)|মাসিক|মান্থলি|\bmonthly\b|"
         r"\b(?:a|one)\s+month\b|এক\s*মাস"), "মাসিক", "monthly"),
    (_re(r"(?<![\d০-৯])(?:15|১৫|পনেরো)\s*(?:দিন|days?\b)"), "পনেরো দিনের", "fifteen-day"),
    (_re(r"(?<![\d০-৯])(?:7|৭|সাত)\s*(?:দিন|days?\b)|সাপ্তাহিক|উইকলি|\bweekly\b|"
         r"\b(?:a|one)\s+week\b|এক\s*সপ্তাহ"), "সাত দিনের", "weekly"),
    (_re(r"(?<![\d০-৯])(?:3|৩|তিন)\s*(?:দিন|days?\b)"), "তিন দিনের", "three-day"),
    (_re(r"(?<![\d০-৯])(?:1|১|এক)\s*(?:দিন|days?\b)|\bdaily\b|ডেইলি|\b(?:a|one)\s+day\b"),
     "এক দিনের", "one-day"),
)
_BUDGET_RE = _re(
    r"বাজেট|টাকার\s*(?:মধ্যে|ভেতরে|ভিতরে|নিচে)|\bbudget\b|\bunder\b|\bwithin\b|\bbelow\b|"
    r"\btakar\s*moddhe\b"
)
_PACK_KIND_BN = {"data": "ডাটা ", "voice": "মিনিট ", "bundle": "কম্বো ", "sms": "এসএমএস ", "pack": ""}
_PACK_KIND_EN = {"data": "data ", "voice": "minute ", "bundle": "combo ", "sms": "SMS ", "pack": ""}

# How much data or how many minutes, echoed as the customer said it (digits
# they said pass safe_filler): "তিন জিবি-র", "১০ জিবি", "100 minutes".
_SIZE_RE = _re(
    r"(?<![\dঀ-৿A-Za-z])([\d০-৯]+|একশো|এক|দুই|দু|তিন|চার|পাঁচ|ছয়|সাত|আট|নয়|দশ|বারো|পনেরো|"
    r"বিশ|পঁচিশ|ত্রিশ|চল্লিশ|পঞ্চাশ|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"twenty|thirty|forty|fifty|hundred)\s*-?\s*(জিবি|গিগা|এমবি|মিনিট|gb|mb|minutes?|mins?)(?![A-Za-z])"
)
_SIZE_UNIT = {  # unit as said -> (Bangla, English)
    "জিবি": ("জিবির", "GB"), "গিগা": ("জিবির", "GB"), "gb": ("জিবির", "GB"),
    "এমবি": ("এমবির", "MB"), "mb": ("এমবির", "MB"),
}

# One package, not a list: "দুই জিবির প্যাকেজটা দেখান", "দুই জিবির অপশনটা",
# "দুই জিবিরটা", "তিন জিবি-র প্যাকেট একটু details বলুন", "the 3 GB package".
# Not "কোন প্যাকেজটা ভালো?", which asks to compare them.
_ONE_PACKAGE_RE = _re(
    r"(?:প্যাকেজ|প্যাকেট|প্যাক|অপশন|package|pack|option)\s*-?\s*(?:টা|টি)|"
    r"(?:জিবি|এমবি|মিনিট)(?:-?র|-?এর|ের)?(?:টা|টি)|"
    r"ডিটেইল|বিস্তারিত|\bdetails?\b|"
    r"\b(?:this|that|the)\s+(?:[\w-]+\s+){0,3}(?:package|pack|option)\b"
)
_WHICH_RE = _re(r"কোন\s*(?:প্যাকেজ|প্যাকেট|প্যাক)|কোনটা|\bwhich\b")


def _one_package(utterance: str) -> bool:
    return bool(_ONE_PACKAGE_RE.search(utterance)) and not _WHICH_RE.search(utterance)


def _negated(utterance: str, start: int, end: int) -> bool:
    """"ত্রিশ দিন না", "not 30 days": the customer named it to rule it out."""
    return bool(
        _PLACE_NEGATED_AFTER_RE.search(utterance[end:end + 30])
        or _PLACE_NEGATED_BEFORE_RE.search(utterance[max(0, start - 12):start])
    )


def _validity(utterance: str) -> tuple[str, str] | None:
    """(Bangla, English) words for the last validity named and not ruled out:
    "ত্রিশ দিন না, এক দিনের" is the one-day."""
    found = [
        (m.start(), bn, en)
        for pattern, bn, en in _VALIDITY
        for m in pattern.finditer(utterance)
        if not _negated(utterance, m.start(), m.end())
    ]
    if not found:
        return None
    _, bn, en = max(found)
    return bn, en


def _size(utterance: str) -> tuple[str, str] | None:
    """(Bangla, English) words for the last data or minutes the customer named
    and didn't rule out."""
    m = next(
        (m for m in reversed(list(_SIZE_RE.finditer(utterance)))
         if not _negated(utterance, m.start(), m.end())),
        None,
    )
    if m is None:
        return None
    number, unit = m.group(1), m.group(2).lower()
    if unit in _SIZE_UNIT:
        bn, en = _SIZE_UNIT[unit]
        return f"{number} {bn}", f"{number} {en}"
    return f"{number} মিনিটের", f"{number}-minute"


def _entity_x(topic: str | None, utterance: str) -> tuple[str, str, str] | None:
    """What the customer asked about, in their own words, for the echo lines,
    and the verb family that fits it: a place for the network or a care
    centre; a validity, size or budget for packages, or the one package they
    mean ("তিন জিবির প্যাকেজটা"). None when they said nothing to echo beyond
    the topic."""
    if topic in ("network", "care"):
        place = _place(utterance)
        if place is None:
            return None
        bn, en = place
        family = _TOPIC_X[topic][2]
        if topic == "network":
            return f"{bn} এলাকার নেটওয়ার্কটা", f"the network in {en}", family
        return f"{bn} এলাকার কেয়ার সেন্টার", f"the care centre nearest {en}", family
    if topic in _PACK_KIND_BN:
        validity = _validity(utterance)
        size = _size(utterance)
        v_bn, v_en = (f"{validity[0]} ", f"{validity[1]} ") if validity else ("", "")
        s_bn, s_en = (f"{size[0]} ", f"{size[1]} ") if size else ("", "")
        if _one_package(utterance):
            if validity is None and size is None:
                return None
            # Looked up, not searched for: "তিন জিবির প্যাকেজটা চেক করে বলছি".
            return f"{v_bn}{s_bn}প্যাকেজটা", f"the {v_en}{s_en}package", "lookup"
        # Three of them make a line over FILLER_MAX_WORDS: the budget goes.
        budget = bool(_BUDGET_RE.search(utterance)) and not (validity and size)
        if validity is None and size is None and not budget:
            return None
        b_bn = "আপনার বাজেটের মধ্যে " if budget else ""
        b_en = " within your budget" if budget else ""
        # "১০০ মিনিটের মিনিট প্যাকেজগুলো" says it twice.
        kind_bn = "" if size and topic == "voice" else _PACK_KIND_BN[topic]
        kind_en = "" if size and topic == "voice" else _PACK_KIND_EN[topic]
        return (
            f"{b_bn}{v_bn}{s_bn}{kind_bn}প্যাকেজগুলো",
            f"the {v_en}{s_en}{kind_en}packages{b_en}",
            _TOPIC_X[topic][2],
        )
    return None


def _speaks_bangla(utterance: str, history: list[Exchange] | None) -> bool:
    script = turn_gate.classify_script(utterance)
    if script == "bn":
        return True
    if _BANGLISH_RE.search(utterance):
        return True
    # A short English word or a number in a Bangla conversation stays Bangla.
    return script == "none" and any(
        turn_gate.classify_script(e.text) == "bn" for e in (history or [])[-4:]
    )


def _opener(line: str) -> str:
    """The line's first word ("জি", "ওকে", "Sure"): two in a row sound canned."""
    first = line.strip().split(",")[0].split()
    return first[0].rstrip("।.!") if first else ""


# A line's shape (_shape): what it is built of, as the ear hears it. Lines
# that differ in words but not in shape still sound like one line reworded.
_TWO_SENTENCES_RE = re.compile(r"[।.!]\s+\S")
_WAIT_END_RE = _re(
    r"(?:এক\s*মিনিট|এক\s*সেকেন্ড|এক\s*মুহূর্ত|সময়\s*দিন|অপেক্ষা\s*করুন|প্লিজ|"
    r"one moment|a moment|one second|please)[।.!]?\s*$"
)
_ACTION_WORD_RE = _re(
    r"জানাচ্ছি|বলছি|দেখাচ্ছি|দিচ্ছি|চেক|দেখে|খুঁজ|যাচাই|খোঁজ|"
    r"(?:check|find|look|pull|get|see|tell|show)"
)


def _shape(line: str) -> str:
    """"wait" (a wait or acknowledgement only: "জি, আমাকে একটু সময় দিন।"),
    "two" (an acknowledgement, then the action: "বুঝতে পেরেছি। ... দেখে
    জানাচ্ছি।"), "wait_end" (the action, then a wait: "... দেখে বলছি, এক
    মিনিট।") or "action" (an opener, then the action: "জি, ... চেক করে বলছি।")."""
    line = unicodedata.normalize("NFC", line.strip())
    if not _ACTION_WORD_RE.search(line):
        return "wait"
    if _TWO_SENTENCES_RE.search(line):
        return "two"
    if _WAIT_END_RE.search(line):
        return "wait_end"
    return "action"


# The verbs a filler ends on; the last one in a line is its main verb ("চেক
# করে জানাচ্ছি" is জানাচ্ছি). Two in a row sound canned too.
# A line's action ("খুঁজে", "চেক করে") and its closing ("আপনাকে জানাচ্ছি"):
# lines in a row differ in both, so they don't sound like one line reworded.
_VERB_RE = _re(
    r"খুঁজ|চেক|বের|দেখে|জেনে|দেখছি|দেখি|নিচ্ছি|প্রসেস|ব্যবস্থা|শুরু|সেকেন্ড|মিনিট|সময়|"
    r"\b(?:check|find|look|pull|get|moment|second|see|set|process|start)"
)
_WAIT_WORDS = {"সেকেন্ড", "মিনিট", "সময়", "moment", "second"}
_CLOSING_RE = _re(r"জানাচ্ছি|বলছি|দেখাচ্ছি|দিচ্ছি")

# "আরও কিছু options দেখান", "এগুলো ছাড়া আর কী আছে?", "আর কি কি options
# available আছে?", "any others?"
_MORE_RE = _re(
    r"আর[ওো]|আর\s*(?:কী|কি)\s*(?:কী|কি)?(?:\s+\S+){0,3}\s*আছে|আর\s*কোনো|বাকিগুলো|অন্য\s*(?:কোনো|কিছু|অপশন)|ছাড়া|"
    r"\bmore\b|\bothers?\b|\banything else\b"
)
# A purchase or recharge asked for, not a question about what exists ("নতুন
# একটা প্যাকেজ নিতে চাচ্ছি, কী কী options আছে?" is a search).
_ACTION_RE = _re(
    r"(?:নিতে|কিনতে)\s*(?:চাই|চাচ্ছি)|কিনব|কিনে\s*(?:দিন|দেন)|অ্যাক্টিভেট|চালু\s*করে\s*দিন|"
    r"রিচার্জ\s*(?:করুন|করেন|করব|করবো|করে\s*দিন)|\b(?:buy|purchase|activate)\b"
)
# More about what was just said, not more options: "আরো বলেন", "tell me
# more". Only with no topic named: "সাত দিনের প্যাকেজটার বিস্তারিত বলুন" echoes it.
_DETAIL_RE = _re(
    r"(?:আর[ওো]|বিস্তারিত)\s*(?:একটু\s*)?(?:বলেন|বলুন|বলো|জানান|বুঝিয়ে)|"
    r"\btell me more\b|\bmore (?:details?|info(?:rmation)?|about (?:it|that|this))\b|"
    r"\bexplain\b|\belaborate\b"
)
_QUESTION_RE = _re(r"(?:কী|কি)\s*(?:কী|কি)|কোন|অপশন|\boptions?\b|\bwhich\b|\bwhat\b|\?")
_PACK_TOPICS = {"data", "voice", "bundle", "sms", "pack"}


def _family(topic: str | None) -> str | None:
    return "pack" if topic in _PACK_TOPICS else topic


def _same_topic(last: str | None, now: str | None) -> bool:
    """Whether `now` continues `last`: the same topic, or a package of no
    named kind ("এই প্যাকেজটি") after one of a kind. Data then minutes is a
    new topic, said as one."""
    if last is None or now is None:
        return False
    return last == now or (_family(last) == _family(now) == "pack" and "pack" in (last, now))


def _verb(line: str) -> str:
    """The line's action, its first verb that isn't a wait ("এক সেকেন্ড"), with
    its closing: "চেক/জানাচ্ছি". A topic may have only two actions; the
    closings keep three lines in a row apart."""
    verbs = [v.lower() for v in _VERB_RE.findall(unicodedata.normalize("NFC", line))]
    action = next((v for v in verbs if v not in _WAIT_WORDS), verbs[0] if verbs else "")
    return f"{action}/{_closing(line)}"


def _closing(line: str) -> str:
    """"জানাচ্ছি", "বলছি", "দেখাচ্ছি" or "দিচ্ছি", or ""."""
    closings = _CLOSING_RE.findall(unicodedata.normalize("NFC", line))
    return closings[-1] if closings else ""


def _tiers(
    utterance: str,
    lookup: str | None,
    bangla: bool,
    last: str | None = None,
    judged: str | None = None,
) -> list[tuple[str, ...]]:
    """The lines that fit this turn, in tiers, best first; [] when only a
    generic line does. First match wins: a correction, a pick from a list, a
    purchase or recharge asked for, more of the same, then the topic, its
    lines in the customer's own words a tier above the plain ones. `last`:
    the filler said before; a follow-up on its topic gets a short line
    ("এটাও দেখে বলছি"), or the new thing it names ("চার জিবির প্যাকেজগুলোও").
    `judged`: Jev's topic for the turn (judged_topic), over the words' topic.
    """
    if _CORRECTION_RE.search(utterance):
        topic = _corrected_topic(utterance)
        if topic is None:
            return [_CORRECTION_BN if bangla else _CORRECTION_EN]
    elif _CHOICE_RE.search(utterance):
        return [_CHOICE_BN if bangla else _CHOICE_EN]
    elif _ACTION_RE.search(utterance) and not _QUESTION_RE.search(utterance):
        return [_ACTION_BN if bangla else _ACTION_EN]
    else:
        topic = _turn_topic(utterance, lookup, judged)
        if topic is None and _DETAIL_RE.search(utterance):
            return [_FOLLOW_UP_BN if bangla else _FOLLOW_UP_EN]
        if _family(topic) in ("pack", None) and _MORE_RE.search(utterance):
            return [_MORE_BN if bangla else _MORE_EN]
        if topic is None:
            return []
    entity = _entity_x(topic, utterance)
    x = None if entity is None else entity[0 if bangla else 1]
    last_topic = None if last is None else _filler_topic(last, None)
    kind = _kind(topic, utterance)
    # "রিচার্জ আসেনি" then "সর্বনিম্ন কত?": a new question, not "সেটাও দেখছি".
    new_kind = kind is not None and last is not None and _line_kind(last) not in (None, kind[0])
    if last is not None and _same_topic(last_topic, topic) and not new_kind:
        last_entity = _entity_x(last_topic, unicodedata.normalize("NFC", last))
        # The same thing said again ("মিরপুরে নেট পাচ্ছি না"), or a problem
        # gone on with: still being checked, not "বিস্তারিত বলছি".
        checking = _CHECKING_BN if bangla else _CHECKING_EN
        if (x is not None and x in last) or _TOPIC_X[topic][2] in ("status", "issue"):
            if x is not None and last_entity is not None and x not in last:
                return [_echo(_FOLLOW_UP_ECHO_BN if bangla else _FOLLOW_UP_ECHO_EN, x), checking]
            return [checking]
        if x is None:
            return [_FOLLOW_UP_BN if bangla else _FOLLOW_UP_EN]
        if last_entity is not None:
            # Something specific after something specific: "চার জিবির…ও".
            echo = _FOLLOW_UP_ECHO_BN if bangla else _FOLLOW_UP_ECHO_EN
            return [_echo(echo, x), _FOLLOW_UP_BN if bangla else _FOLLOW_UP_EN]
    tiers = [_topic_lines(topic, bangla)]
    if kind is not None:
        # Its own lines only: the topic's plain ones are about another
        # question ("কত পয়েন্ট জমেছে" for how points are earned).
        tiers = [kind[1] if bangla else kind[2]]
    elif topic in _KINDS and topic not in _PLAIN_FITS:
        # "রিচার্জের process টা জানতে চাচ্ছিলাম" in words no kind knows.
        return []
    if entity is not None:
        tiers.insert(0, _echo((_ECHO_BN if bangla else _ECHO_EN)[entity[2]], x))
    elif topic in _PACK_KIND_BN and _one_package(utterance):
        # One package, but not which: "প্যাকেজটার details বলুন".
        tiers.insert(0, _CHOICE_BN if bangla else _CHOICE_EN)
    elif topic == "pack" and not _WHICH_RE.search(utterance):
        # "কী কী প্যাকেজ আছে?" gets no filler (broad_package_ask); should one
        # be asked for, a generic line, not "প্যাকেজগুলো খুঁজে বলছি".
        return []
    return tiers


def broad_package_ask(utterance: str) -> bool:
    """"কী কী প্যাকেজ আছে?": packages, with no kind, size, validity, budget or
    one package named, and not a pick, a correction, more of a list or "which
    one". The main model asks what kind before it searches (prompt_defaults
    STYLE), so the turn needs no filler."""
    utterance = unicodedata.normalize("NFC", utterance)
    if _filler_topic(utterance, None) != "pack":
        return False
    if any(r.search(utterance) for r in (_CORRECTION_RE, _CHOICE_RE, _MORE_RE, _WHICH_RE, _ACTION_RE)):
        return False
    return _entity_x("pack", utterance) is None and not _one_package(utterance)


# Shared by every session; tests pass their own, seeded.
_RNG = random.Random()


def fast_filler(
    utterance: str,
    lookup: str | None,
    history: list[Exchange] | None = None,
    avoid: list[str] | None = None,
    *,
    cache: AudioCache | None = None,
    rng: random.Random | None = None,
    topic: str | None = None,
    language: ReplyLanguage | None = None,
) -> str | None:
    """A template filler for the turn, in well under a millisecond, or None
    when the utterance is empty. Picks at random, so a call doesn't open with
    the same line every time, from:
    - the best tier that still has a line not said in the last few turns
      (_tiers: the customer's own words, the topic, then generic lines);
    - within it, the lines that open and end on other words than the last
      fillers, and are built another way than the last one (_shape), when
      there are any;
    - weighted towards a line whose audio is already cached.
    topic: Jev's for the turn (judged_topic), else the words decide.
    language: the customer's picked reply language; else their words decide."""
    if not utterance.strip():
        return None
    utterance = unicodedata.normalize("NFC", utterance)
    bangla = language == "bn" if language else _speaks_bangla(utterance, history)
    avoid = avoid or []
    last = avoid[-1] if avoid else None
    tiers = [
        *_tiers(utterance, lookup, bangla, last, topic),
        _GENERIC_BN if bangla else _GENERIC_EN,
    ]

    def usable(line: str) -> bool:
        return safe_filler(line, utterance) is not None and reply_language.fits(line, language)

    pool = next(
        (fresh for tier in tiers if (fresh := [x for x in tier if x not in avoid and usable(x)])),
        None,
    )
    if pool is None:
        # Every line was said lately: anything but the very last one.
        pool = [x for tier in tiers for x in tier if (not avoid or x != avoid[-1]) and usable(x)]
        if not pool:
            return None
    recent_openers = {_opener(line) for line in avoid[-3:]}
    recent_verbs = {_verb(line) for line in avoid[-2:]}
    last_closing = _closing(avoid[-1]) if avoid else ""
    last_shape = _shape(avoid[-1]) if avoid else ""

    def fresh(x: str) -> bool:
        return _opener(x) not in recent_openers and _verb(x) not in recent_verbs

    def new_shape(x: str) -> bool:
        return _shape(x) != last_shape

    for keep in (
        lambda x: fresh(x) and new_shape(x) and not (last_closing and _closing(x) == last_closing),
        lambda x: fresh(x) and new_shape(x),
        fresh,
        lambda x: _opener(x) not in recent_openers,
    ):
        if narrowed := [x for x in pool if keep(x)]:
            pool = narrowed
            break
    weights = [1.5 if cache is not None and cache.has_line(x) else 1.0 for x in pool]
    return (rng or _RNG).choices(pool, weights)[0]


# Every fixed line, for the audio cache; a line echoing the customer's own
# words joins when it is said (remember_filler).
_FILLER_LINES: set[str] = {
    normalize_text(line)
    for lines in (
        _GENERIC_BN,
        _GENERIC_EN,
        _CORRECTION_BN,
        _CORRECTION_EN,
        _CHOICE_BN,
        _CHOICE_EN,
        _FOLLOW_UP_BN,
        _FOLLOW_UP_EN,
        _MORE_BN,
        _MORE_EN,
        _ACTION_BN,
        _ACTION_EN,
        *(_topic_lines(topic, bangla) for topic in _TOPIC_X for bangla in (True, False)),
        *(lines for rows in _KINDS.values() for row in rows for lines in row[2:]),
    )
    for line in lines
}


def remember_filler(line: str) -> None:
    """A line the small model wrote: its audio may be cached too."""
    _FILLER_LINES.add(normalize_text(line))


def is_filler_line(text: str) -> bool:
    """Whether a sentence the TTS is asked for is a filler line (template or
    written by the small model), whose audio app.agent.audio_cache keeps."""
    return normalize_text(text) in _FILLER_LINES


def quick_on(config: ResolvedAgentConfig) -> bool:
    return config.quick_reply_enabled and (config.quick_fast_answer or config.quick_filler)


# A turn the main model answers with an account tool or a lookup (balance,
# usage, packs, recharge, offers, deductions, network, a care centre, a
# complaint, how or why):
# worth a filler even when Jev says no lookup runs before the LLM.
_NEEDS_TOOL_RE = re.compile(
    r"ব্যালেন্স|ডাটা|ডেটা|ইন্টারনেট|মিনিট|এসএমএস|প্যাক|প্যাকেজ|রিচার্জ|অফার|পয়েন্ট|পয়েন্ট|"
    r"রিডিম|বিল|লেনদেন|কেটে|কাটল|কাটা|নেটওয়ার্ক|নেটওয়ার্ক|সিগন্যাল|অভিযোগ|সমস্যা|ইউসেজ|"
    r"মেয়াদ|মেয়াদ|রোমিং|সিম|কেন|কীভাবে|কিভাবে|"
    r"কে(?:\u09df|\u09af\u09bc)ার|সেন্টার|ব্রাঞ্চ|শোরুম|"
    r"\b(?:balance|data|internet|minutes?|sms|packs?|packages?|recharge|top\s*up|offers?|"
    r"points?|redeem|bill|transactions?|deduct\w*|charged?|network|signal|complaint|problem|"
    r"usage|validity|roaming|sim|why|how|branch(?:es)?|showrooms?)\b|"
    r"\bcustomer\s*care\b|\bcare\s*cent(?:re|er)s?\b|"
    r"\b(?:koto|keno|kivabe|kete|takar)\b",
    re.I,
)


# ---- guest replies ----
#
# A guest (no subscriber_id) asking about their own account, to recharge, to
# buy a package or for a person gets a fixed line at once: it needs a login, so a filler ("ব্যালেন্সটা দেখে বলছি") followed by
# "please log in" would promise a lookup that never comes. Each line says
# where to log in and that the answer comes right after; some offer what the
# agent can do meanwhile. One asking for a person hears empathy first, then the
# hotline, since no case can be opened for a guest. Only a turn Jev is sure about, on one topic, gets
# one; anything else is the main model's, which follows GUEST_SNAPSHOT.

# Words a guest topic needs besides Jev's topic: "কত পয়েন্ট আছে" is their own
# points, "পয়েন্ট কীভাবে পাব" is answered for anyone.
_OWN_PACK_RE = _re(
    r"আমার\s*(?:এখন(?:কার)?\s*)?(?:কোন\s*)?(?:ডাটা\s*|মিনিট\s*)?(?:প্যাক|প্যাকেজ)|"
    r"(?:চালু|অ্যাক্টিভ|এক্টিভ)\s*(?:আছে\s*)?(?:কোন\s*)?(?:প্যাক|প্যাকেজ)|"
    r"(?:প্যাক|প্যাকেজ)\S*\s*(?:চালু|অ্যাক্টিভ|এক্টিভ)|"
    r"\bmy\s+(?:current\s+|active\s+)?(?:data\s+|minute\s+)?(?:packs?|packages?)\b|"
    r"\bwhich\s+(?:pack|package)s?\s+(?:do\s+)?i\s+have\b|"
    r"\b(?:packs?|packages?)\s+(?:i\s+have|i'?m\s+on)\b"
)
_OWN_POINTS_RE = _re(
    r"কত\s*(?:রিওয়ার্ড\s*)?পয়েন্ট|পয়েন্ট\S*\s*(?:কত|কয়টা)|আমার\s*(?:রিওয়ার্ড\s*)?পয়েন্ট|"
    r"\bhow\s+many\s+(?:reward\s+)?points\b|\bmy\s+(?:reward\s+)?points\b|\bpoints?\s+balance\b"
)
_RECHARGE_STATUS_RE = _re(
    r"(?:আসেনি|আসে\s*নি|আসেনাই|পাইনি|পাই\s*নি|পাই\s*নাই|যোগ\s*হয়নি|যোগ\s*হয়\s*নি|ঢোকেনি|"
    r"আসছে\s*না|হয়নি|হয়\s*নি)|(?:শেষ|লাস্ট|আগের)\s*রিচার্জ|রিচার্জ\S*\s*(?:হিস্ট্রি|হিসাব)|"
    r"\b(?:didn'?t|did\s+not|hasn'?t|has\s+not|never)\s+(?:arrive|come|reach|get|show)|"
    r"\bnot\s+(?:received|credited|arrived)\b|\b(?:last|previous)\s+recharges?\b|"
    r"\brecharge\s+history\b"
)
_CASE_RE = _re(r"কেস|\bcase\s*(?:status|number|update)|\bmy\s+cases?\b|\bTC-?\d+")
# Doing a recharge (not asking how): "রিচার্জ করে দিন", "I want to top up".
_RECHARGE_DO_RE = _re(
    r"রিচার্জ\s*(?:টা\s*)?(?:করব|করবো|করতে\s*চাই|করতে\s*চাচ্ছি|করে\s*(?:দিন|দাও|দেন))|"
    r"\b(?:want|like|need)\s+to\s+(?:recharge|top\s*up)\b|\b(?:recharge|top\s*up)\s+(?:my|me)\b|"
    r"\brecharge\s+(?:korbo|korte\s+chai|kore\s+(?:den|dao|din))\b"
)
# Buying a package: "এটা কিনব", "প্যাকেজটা নিতে চাই", "I'll buy it".
_BUY_RE = _re(
    r"কিন(?:ব|বো|তে\s*চাই|তে\s*চাচ্ছি|ে\s*(?:দিন|দাও|দেন))|"
    r"(?:প্যাক|প্যাকেজ)\S*\s*(?:টা\s*)?(?:নিব|নেব|নিবো|নেবো|নিতে\s*চাই|চালু\s*করে\s*(?:দিন|দাও|দেন))|"
    r"\b(?:buy|purchase|activate)\b|\bsubscribe\s+to\b|\bkinbo\b|\bkinte\s+chai\b"
)
# Asking for a person: "মানুষের সাথে কথা বলতে চাই", "talk to a human".
_HUMAN_RE = _re(
    r"(?:মানুষ|এজেন্ট|প্রতিনিধি|অফিসার|কর্মকর্তা|সুপারভাইজার)\S*\s*(?:এর\s*)?(?:সাথে|সঙ্গে)|"
    r"কোনো\s*মানুষ|আসল\s*মানুষ|(?:কারো|কারোর|কারও)\s*(?:সাথে|সঙ্গে)\s*কথা|"
    r"\b(?:talk|speak|chat)\s+(?:to|with)\s+(?:a\s+|an\s+|your\s+)?(?:human|person|someone|agent|"
    r"representative|supervisor|manager)\b|\b(?:real|actual)\s+person\b|\b(?:human|live)\s+agent\b"
)


# "কীভাবে রিচার্জ করব?" asks how, for anyone: the knowledge base.
_HOW_RE = _re(r"কীভাবে|কিভাবে|কেমনে|কি\s*ভাবে|how|kivabe")


def _buy_by_spec(utterance: str) -> bool:
    """A buy that names what it wants ("৩০০ টাকার মধ্যে ডাটা প্যাকেজ কিনব"):
    the main model searches, then says buying needs a login."""
    return (
        broad_package_ask(utterance)
        or _size(utterance) is not None
        or _validity(utterance) is not None
        or bool(_NUMBER_RE.search(utterance))
    )

# Guest topic: (Jev topics it follows, None among them when the words are
# enough without Jev; the words it needs or None; the word topics (_TOPIC_RES)
# the turn may also match, any other being a second ask, or None for any).
# First match wins: a person first, whatever else they say.
_PACK_JEV = frozenset({"pack", "data", "voice", "bundle", "sms", "usage"})
_PACKS = frozenset({"pack", "data", "voice", "bundle", "sms"})
_GUEST_TOPICS: dict[
    str, tuple[frozenset[str | None], re.Pattern[str] | None, frozenset[str] | None]
] = {
    "human": (frozenset({None, *_TOPIC_X}), _HUMAN_RE, None),
    "recharge_do": (
        frozenset({None, "recharge", "balance"}), _RECHARGE_DO_RE, frozenset({"recharge", "balance"})
    ),
    "buy": (frozenset({None, "offer", *_PACK_JEV}), _BUY_RE, frozenset({"offer", "balance", *_PACKS})),
    "balance": (frozenset({"balance"}), None, frozenset({"balance"})),
    "usage": (frozenset({"usage"}), None, frozenset({"usage", "balance"})),
    "my_pack": (_PACK_JEV, _OWN_PACK_RE, frozenset({"pack", "data", "voice", "bundle", "sms", "usage"})),
    "transactions": (frozenset({"transactions"}), None, frozenset({"transactions", "balance"})),
    "recharge": (frozenset({"recharge"}), _RECHARGE_STATUS_RE, frozenset({"recharge", "balance"})),
    "points": (frozenset({"points"}), _OWN_POINTS_RE, frozenset({"points"})),
    "offer": (frozenset({"offer"}), None, frozenset({"offer"})),
    "case": (frozenset({"complaint"}), _CASE_RE, frozenset({"complaint"})),
}

_GUEST_LINES: dict[str, dict[ReplyLanguage, tuple[str, ...]]] = {
    "balance": {
        "bn": (
            "ব্যালেন্সটা আপনার অ্যাকাউন্ট থেকে দেখতে হয়। ওপরের Log in বাটনে লগইন করলেই সাথে সাথে বলে দিচ্ছি।",
            "জি, ব্যালেন্স দেখতে একবার লগইন করে নিতে হবে। ওপরের Log in বাটনে লগইন করলেই জানিয়ে দিচ্ছি। ততক্ষণ চাইলে প্যাকেজ খুঁজে দিতে পারি।",
        ),
        "en": (
            "Your balance is on your account, so I'll need you to log in first. Use the Log in button at the top and I'll tell you right away.",
            "Sure, once you log in with the Log in button at the top, I'll check your balance straight away. Meanwhile, I can help you find a package.",
        ),
    },
    "usage": {
        "bn": (
            "কতটুকু ডাটা বা মিনিট বাকি, সেটা আপনার অ্যাকাউন্টে দেখা যায়। ওপরের Log in বাটনে লগইন করলেই বলে দিচ্ছি।",
            "জি, ইউসেজ দেখতে আগে লগইন করে নিতে হবে। লগইন হলেই হিসাবটা জানিয়ে দিচ্ছি। ততক্ষণ চাইলে নতুন প্যাকেজ খুঁজে দিতে পারি।",
        ),
        "en": (
            "Your data and minutes left are on your account. Log in with the button at the top and I'll tell you right away.",
            "Sure, I'll need you to log in first to see your usage. Once you do, I'll go through it with you. Meanwhile, I can help you find a new package.",
        ),
    },
    "my_pack": {
        "bn": (
            "আপনার এখনকার প্যাকেজটা অ্যাকাউন্ট থেকে দেখতে হয়। ওপরের Log in বাটনে লগইন করলেই বলে দিচ্ছি।",
            "জি, কোন প্যাকেজ চালু আছে দেখতে একবার লগইন করে নিতে হবে। ততক্ষণ চাইলে নতুন প্যাকেজগুলো দেখাতে পারি।",
        ),
        "en": (
            "Your current package is on your account, so please log in first with the button at the top. I'll tell you right after.",
            "Sure, I'll need you to log in to see which package you're on. Meanwhile, I can show you the packages we have.",
        ),
    },
    "transactions": {
        "bn": (
            "লেনদেনগুলো দেখতে আগে লগইন করে নিতে হবে। ওপরের Log in বাটনে লগইন করলেই কোথায় কত কাটল, দেখে বলছি।",
            "জি, কোন টাকা কীসে কাটল, সেটা আপনার অ্যাকাউন্ট থেকে দেখতে হয়। লগইন করলেই সাথে সাথে বুঝিয়ে বলছি।",
        ),
        "en": (
            "Your transactions are on your account, so please log in first with the button at the top. I'll go through the charges right after.",
            "Sure, once you log in I can see exactly what was charged and explain each one.",
        ),
    },
    "recharge": {
        "bn": (
            "রিচার্জটা ঠিকমতো এসেছে কিনা, সেটা আপনার অ্যাকাউন্ট থেকে দেখতে হয়। ওপরের Log in বাটনে লগইন করলেই চেক করে দিচ্ছি।",
            "জি, রিচার্জের হিসাব দেখতে আগে লগইন করে নিতে হবে। লগইন হলেই সাথে সাথে দেখে দিচ্ছি।",
        ),
        "en": (
            "Your recharges are on your account, so please log in first with the button at the top. I'll check it right after.",
            "Sure, once you log in I'll look up your recharge straight away.",
        ),
    },
    "points": {
        "bn": (
            "আপনার কত পয়েন্ট আছে, সেটা দেখতে লগইন করে নিতে হবে। ওপরের Log in বাটনে লগইন করলেই বলে দিচ্ছি।",
            "জি, পয়েন্টগুলো আপনার অ্যাকাউন্টে থাকে। লগইন করলেই কত আছে আর কীসে খরচ করা যায়, জানিয়ে দিচ্ছি।",
        ),
        "en": (
            "Your points are on your account, so please log in first with the button at the top. I'll tell you right after.",
            "Sure, once you log in I'll tell you how many points you have and what you can use them for.",
        ),
    },
    "offer": {
        "bn": (
            "আপনার জন্য কোন অফারগুলো আছে, সেটা অ্যাকাউন্ট দেখে বলতে হয়। ওপরের Log in বাটনে লগইন করলেই জানিয়ে দিচ্ছি।",
            "জি, অফারগুলো একেকজনের জন্য একেক রকম, তাই আগে লগইন করে নিতে হবে। ততক্ষণ চাইলে প্যাকেজগুলো দেখাতে পারি।",
        ),
        "en": (
            "Offers depend on your account, so please log in first with the button at the top. I'll show you yours right after.",
            "Sure, offers differ from one customer to the next, so I'll need you to log in first. Meanwhile, I can show you our packages.",
        ),
    },
    # {phone}: the operator's hotline; with none set, "human" uses _GUEST_HUMAN_NO_PHONE.
    "human": {
        "bn": (
            "আপনার অসুবিধার জন্য সত্যিই দুঃখিত। চাইলে এখনই {phone} হটলাইনে কল করে আমাদের টিমের সাথে সরাসরি কথা বলতে পারেন। আর ওপরের Log in বাটনে লগইন করলে আমি টিমের কাছে রিকোয়েস্টও পাঠিয়ে দিতে পারি।",
            "আপনার কথা বুঝতে পেরেছি, এমন ঝামেলার জন্য সরি। আমাদের টিমের সাথে সরাসরি কথা বলতে {phone} নম্বরে কল করতে পারেন। লগইন করলে আমিও টিমের কাছে পাঠিয়ে দিতে পারি, একজন ফলো আপ করবেন।",
        ),
        "en": (
            "I'm really sorry for the trouble. You can call our hotline at {phone} to speak with our team directly, or log in with the button at the top and I'll send them a request to follow up.",
            "I understand, and I'm sorry this has been frustrating. Our team is on {phone} if you'd like to talk to them now. If you log in, I can also pass this to them for a follow-up.",
        ),
    },
    "recharge_do": {
        "bn": (
            "রিচার্জ করতে হলে আগে লগইন করে নিতে হবে। ওপরের Log in বাটনে লগইন করলেই রিচার্জটা করে দিচ্ছি।",
            "জি, রিচার্জের জন্য আপনার অ্যাকাউন্টে লগইন থাকতে হবে। ওপরের Log in বাটনে লগইন করে নিন, তারপর সাথে সাথে করে দিচ্ছি।",
        ),
        "en": (
            "To recharge, you'll need to log in first. Use the Log in button at the top and I'll do the recharge right after.",
            "Sure, a recharge needs you to be logged in. Once you log in with the button at the top, I'll take care of it straight away.",
        ),
    },
    "buy": {
        "bn": (
            "প্যাকেজ কিনতে হলে আগে লগইন করে নিতে হবে। ওপরের Log in বাটনে লগইন করলেই প্যাকেজটা কেনার ব্যবস্থা করে দিচ্ছি।",
            "জি, প্যাকেজ কেনার জন্য আপনার অ্যাকাউন্টে লগইন থাকতে হবে। ওপরের Log in বাটনে লগইন করে নিন, তারপর সাথে সাথে করে দিচ্ছি।",
        ),
        "en": (
            "To buy a package, you'll need to log in first. Use the Log in button at the top and I'll set it up for you right after.",
            "Sure, buying a package needs you to be logged in. Once you log in with the button at the top, I'll take care of it straight away.",
        ),
    },
    "case": {
        "bn": (
            "আপনার কেসের খবর দেখতে আগে লগইন করে নিতে হবে। ওপরের Log in বাটনে লগইন করলেই আপডেটটা বলে দিচ্ছি।",
            "জি, কেসগুলো আপনার অ্যাকাউন্টের সঙ্গে থাকে। লগইন করলেই সাথে সাথে দেখে বলছি।",
        ),
        "en": (
            "Your cases are on your account, so please log in first with the button at the top. I'll give you the update right after.",
            "Sure, once you log in I'll check on your case straight away.",
        ),
    },
}


def is_guest(userdata: object) -> bool:
    """A session with no account: subscriber_id there and None."""
    return hasattr(userdata, "subscriber_id") and getattr(userdata, "subscriber_id") is None


_GUEST_HUMAN_NO_PHONE: dict[ReplyLanguage, tuple[str, ...]] = {
    "bn": (
        "আপনার অসুবিধার জন্য সত্যিই দুঃখিত। ওপরের Log in বাটনে লগইন করলেই আমাদের টিমের কাছে রিকোয়েস্ট পাঠিয়ে দিচ্ছি, একজন আপনার সাথে যোগাযোগ করবেন।",
        "আপনার কথা বুঝতে পেরেছি, এমন ঝামেলার জন্য সরি। লগইন করলেই টিমের কাছে পাঠিয়ে দিচ্ছি, একজন ফলো আপ করবেন।",
    ),
    "en": (
        "I'm really sorry for the trouble. Once you log in with the button at the top, I'll send our team a request and someone will follow up with you.",
        "I understand, and I'm sorry this has been frustrating. If you log in, I'll pass this to our team straight away for a follow-up.",
    ),
}


def _word_topics(utterance: str) -> set[str]:
    """Every topic the words name (_TOPIC_RES), not just the first."""
    utterance = unicodedata.normalize("NFC", utterance)
    return {_PACK_KIND_TOPIC.get(name, name) for name, pattern in _TOPIC_RES if pattern.search(utterance)}


def guest_topic(
    judgement: Judgement | None, userdata: object, settings: Settings, text: str | None = None
) -> str | None:
    """The guest topic (_GUEST_TOPICS) of a guest's turn about their own
    account, or None: not a guest, Jev not sure, a lookup to run, or a second
    ask in the same turn."""
    if judgement is None or not is_guest(userdata):
        return None
    if judgement.lookup != "none":
        return None
    judged = judged_topic(judgement, settings)
    utterance = unicodedata.normalize("NFC", text or judgement.text or "")
    words = _word_topics(utterance)
    for name, (jev, needs, allowed) in _GUEST_TOPICS.items():
        if judged not in jev or (needs is not None and not needs.search(utterance)):
            continue
        if name in ("recharge_do", "buy") and _HOW_RE.search(utterance):
            return None
        if name == "buy" and _buy_by_spec(utterance):
            return None
        if allowed is not None and words - allowed:
            return None
        return name
    return None


def guest_line(
    topic: str,
    utterance: str,
    language: ReplyLanguage | None,
    said: Sequence[str],
    phone: str = "",
) -> str:
    """One of the topic's lines in the picked language (else the utterance's
    script), not the one said last if there is another. phone: the hotline
    the "human" lines offer."""
    lang: ReplyLanguage = language or ("en" if turn_gate.classify_script(utterance) == "en" else "bn")
    if topic == "human" and not phone.strip():
        lines = _GUEST_HUMAN_NO_PHONE[lang]
    else:
        lines = tuple(line.format(phone=phone.strip()) for line in _GUEST_LINES[topic][lang])
    fresh = [line for line in lines if line not in said[-_AVOID:]]
    return random.choice(fresh or list(lines))


# Word topics a guest can't be answered on without a login.
_GUEST_ACCOUNT_WORDS = frozenset({"balance", "usage", "transactions", "offer"})


def guest_account_ask(userdata: object, utterance: str) -> bool:
    """Whether a guest's turn asks about their own account by its words alone.
    It gets no filler, template or model-written: any "let me check" would
    promise a lookup the login guidance then takes back."""
    if not is_guest(userdata):
        return False
    utterance = unicodedata.normalize("NFC", utterance)
    if _word_topics(utterance) & _GUEST_ACCOUNT_WORDS:
        return True
    if _HUMAN_RE.search(utterance):
        return True
    own = (_OWN_PACK_RE, _OWN_POINTS_RE, _RECHARGE_STATUS_RE, _CASE_RE)
    if _HOW_RE.search(utterance):
        # How to recharge or buy is for anyone; only their own account isn't.
        return any(pattern.search(utterance) for pattern in own)
    if _BUY_RE.search(utterance) and not _buy_by_spec(utterance):
        return True
    return any(pattern.search(utterance) for pattern in (*own, _RECHARGE_DO_RE))


def early_filler(text: str, userdata: object, config: ResolvedAgentConfig) -> bool:
    """Whether a model-written line (quick_filler_llm) can start on the final
    transcript, before Jev answers: the words alone route the turn to a filler
    (route). The line is spoken only if Jev's answer routes it there too.
    Template lines are instant, so they never start early."""
    if not (config.quick_reply_enabled and config.quick_filler and config.quick_filler_llm):
        return False
    if getattr(userdata, "pending_action", None) or getattr(userdata, "pending_case", None):
        return False
    if guest_account_ask(userdata, text):
        return False
    return not broad_package_ask(text) and bool(_NEEDS_TOOL_RE.search(text))


def route(
    judgement: Judgement | None,
    userdata: object,
    config: ResolvedAgentConfig,
    settings: Settings,
    *,
    text: str | None = None,
    closing: bool = False,
) -> Route | None:
    """Which quick path an accepted turn takes; None = the main model, as
    without quick replies. closing: the gate took the turn as a goodbye
    (turn_gate.is_closing) without asking Jev -- it needs no lookup, and ending
    the call is the one tool the small model has. text: the turn (else the
    judgement's): one that needs a tool gets a filler whatever Jev's lookup."""
    if not config.quick_reply_enabled:
        return None
    # An OTP or a yes/no for a waiting action, or a case being drafted, belongs to
    # the main model, which owns the tools; Jev may well say "none" for it.
    if getattr(userdata, "pending_action", None) or getattr(userdata, "pending_case", None):
        return None
    if closing:
        if config.quick_fast_answer:
            return "fast"
        return None
    if judgement is None or judgement.lookup is None:
        return None
    lookup_p = judgement.lookup_p or 0.0
    turn_text = text or judgement.text or ""
    if guest_topic(judgement, userdata, settings, turn_text) is not None:
        return "guest"
    if guest_account_ask(userdata, turn_text):
        # No filler: the small model gives the login line (FAST_GUEST_RULES)
        # or hands off to the main model, which has GUEST_SNAPSHOT.
        return "fast" if config.quick_fast_answer else None
    if broad_package_ask(turn_text):
        # The reply is a question back ("কোন ধরনের প্যাকেজ?"), at once: a
        # "একটু সময় দিন" before it promises a lookup that never comes.
        return None
    if config.quick_filler and _NEEDS_TOOL_RE.search(turn_text):
        return "filler"
    if judgement.lookup == "none":
        if config.quick_fast_answer and lookup_p >= settings.quick_route_min_p:
            return "fast"
        return None
    # A weak guess at a search gets no "let me find that": the main model may
    # well ask a question instead.
    if config.quick_filler and lookup_p >= settings.router_min_p:
        return "filler"
    return None


def build_fast_llm(config: ResolvedAgentConfig, settings: Settings, api_key: str) -> llm.LLM:
    from livekit.plugins import openai

    return openai.LLM(
        model=config.quick_reply_model,
        api_key=api_key,
        base_url=settings.openrouter_base_url,
        temperature=config.temperature,
        max_completion_tokens=config.max_output_tokens,
        extra_body={"reasoning": reasoning_for(config.quick_reply_model)},
    )


def end_call_tools(tools: Sequence[llm.Tool]) -> list[llm.Tool]:
    """A new list with only the end_call tool: the caller's list is synced back
    into the turn's tools by the library, so it must not change."""
    return [tool for tool in tools if isinstance(tool, llm.FunctionTool) and tool.id == "end_call"]


def fast_rules(language: ReplyLanguage | None = None, *, guest: bool = False) -> str:
    """FAST_RULES, with the language line naming the picked language, if any:
    the rules come last, so their "customer's latest message" would win.
    guest: with FAST_GUEST_RULES."""
    rules = FAST_RULES + FAST_GUEST_RULES if guest else FAST_RULES
    if language is None:
        return rules
    return rules.replace(
        _FAST_LANGUAGE_LINE,
        f"Reply only in {reply_language.name(language)}, whatever language the customer used "
        "(REPLY LANGUAGE above).",
    )


def fast_chat_ctx(
    chat_ctx: llm.ChatContext, language: ReplyLanguage | None = None, *, guest: bool = False
) -> llm.ChatContext:
    """The conversation for the small model: the agent's instructions plus
    FAST_RULES, without tool calls (fewer tokens, and no other model's tool
    calls for it to choke on). copy() is shallow, so the instructions message is
    replaced, never changed in place -- that would put FAST_RULES into the main
    model's prompt for the rest of the call."""
    rules = fast_rules(language, guest=guest)
    ctx = chat_ctx.copy(exclude_function_call=True)
    idx = ctx.index_by_id(INSTRUCTIONS_MESSAGE_ID)
    if idx is not None and ctx.items[idx].type == "message":
        old = ctx.items[idx]
        ctx.items[idx] = llm.ChatMessage(
            id=INSTRUCTIONS_MESSAGE_ID,
            role="system",
            content=[(old.text_content or "") + rules],
            created_at=old.created_at,
        )
    else:
        ctx.items.insert(
            0, llm.ChatMessage(id=INSTRUCTIONS_MESSAGE_ID, role="system", content=[rules])
        )
    return ctx


class Handoff(Exception):
    """The small model can't answer this turn: the main model should."""


async def stream_fast(
    fast_llm: llm.LLM,
    chat_ctx: llm.ChatContext,
    tools: Sequence[llm.Tool],
    *,
    buffer_chars: int,
    first_chunk_timeout_s: float,
) -> AsyncIterator[llm.ChatChunk | str]:
    """The small model's answer. Raises Handoff before yielding anything when it
    writes HANDOFF, fails, is too slow to start, or says nothing. The first
    buffer_chars are held back so a HANDOFF is never spoken; once text has gone
    out a later error just ends the answer."""
    held = ""
    yielded = False
    try:
        async with fast_llm.chat(
            chat_ctx=chat_ctx, tools=list(tools), conn_options=APIConnectOptions(max_retry=0)
        ) as stream:
            chunks = stream.__aiter__()
            first = True
            while True:
                try:
                    if first:
                        async with asyncio.timeout(first_chunk_timeout_s):
                            chunk = await chunks.__anext__()
                        first = False
                    else:
                        chunk = await chunks.__anext__()
                except StopAsyncIteration:
                    break
                delta = chunk.delta
                if delta is None:
                    continue
                if delta.tool_calls:
                    if HANDOFF in held:
                        raise Handoff()
                    if held:
                        yield held.replace(HANDOFF, "")
                        held = ""
                    yielded = True
                    yield chunk
                    continue
                text = delta.content or ""
                if not text:
                    continue
                if yielded:
                    out, held = _split_marker_tail((held + text).replace(HANDOFF, ""))
                    if out:
                        yield out
                    continue
                held += text
                if HANDOFF in held:
                    raise Handoff()
                if len(held) >= buffer_chars:
                    # A HANDOFF cut in two stays held until the rest shows it.
                    out, held = _split_marker_tail(held)
                    if out:
                        yielded = True
                        yield out
    except Handoff:
        raise
    except Exception as exc:
        if not yielded:
            raise Handoff() from exc
        logger.warning("fast answer stopped early: %s", exc)
        return
    if not yielded:
        if HANDOFF in held or not held.strip():
            raise Handoff()
    if held:
        yield held


def _split_marker_tail(text: str) -> tuple[str, str]:
    """(text to say, a trailing start of HANDOFF to hold back)."""
    for size in range(min(len(HANDOFF) - 1, len(text)), 0, -1):
        if text.endswith(HANDOFF[:size]):
            return text[:-size], text[-size:]
    return text, ""


def safe_filler(text: str, utterance: str, max_words: int = FILLER_MAX_WORDS) -> str | None:
    """The line, if it is one: short, and stating no number, price or contact of
    its own (which could only be a guess -- nothing has been looked up yet).
    Numbers the customer said may be echoed."""
    text = " ".join(text.split())
    if not text or len(text.split()) > max_words:
        return None
    if _CONTACT_RE.search(text):
        return None
    if not set(_NUMBER_RE.findall(text)) <= set(_NUMBER_RE.findall(utterance)):
        return None
    # "কত টাকা রিচার্জ করা যায়" asks about an amount without naming one.
    if _MONEY_RE.search(_HOW_MUCH_RE.sub("", text)) and not _MONEY_RE.search(utterance):
        return None
    if text.rstrip().endswith(("?", "？")):
        return None
    return text


def build_filler_request(
    model: str,
    utterance: str,
    lookup: str | None,
    history: list[Exchange],
    avoid: list[str],
    topic: str | None = None,
    care: bool = False,
    language: ReplyLanguage | None = None,
    guest: bool = False,
) -> dict:
    """guest: the customer isn't logged in (_FILLER_GUEST_NOTE). care: the model writes every line (_CARE_FILLER_SYSTEM), sampled so
    turns alike don't get the same line; else it fills in for the templates.
    language: the customer's picked reply language, which outranks the
    system prompt's "match the customer's newest message"."""
    lines = ["Conversation so far:"]
    lines += [f"{'Customer' if e.role == 'user' else 'Assistant'}: {e.text}" for e in history]
    if not history:
        lines.append("(none yet)")
    if lookup:
        lines.append(f"What is being looked up: {lookup.replace('_', ' ')}.")
    if topic in _TOPIC_X:
        lines.append(f"What the customer asks about: {_TOPIC_X[topic][1]}.")
    if avoid:
        lines.append("Already said (don't repeat): " + " | ".join(avoid))
    lines.append(f"Customer's new message: {utterance}")
    if guest:
        lines.append(_FILLER_GUEST_NOTE)
    if language:
        lines.append(
            f"LANGUAGE: write the line in {reply_language.name(language)}, "
            "whatever language the customer used."
        )
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": _CARE_FILLER_SYSTEM if care else _FILLER_SYSTEM},
            {"role": "user", "content": "\n".join(lines)},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.8 if care else 0,
        "max_tokens": 120,
        "reasoning": reasoning_for(model),
        # Customer speech: keep it out of provider training data.
        "provider": {"sort": "latency", "data_collection": "deny"},
    }


async def compose_filler(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    model: str,
    utterance: str,
    lookup: str | None,
    history: list[Exchange],
    avoid: list[str],
    *,
    timeout_s: float,
    on_event: Callable[[str], None] | None = None,
    topic: str | None = None,
    care: bool = False,
    language: ReplyLanguage | None = None,
    guest: bool = False,
) -> str | None:
    """A filler line for the turn, or None on any error, timeout or unsafe line
    (one in another language than the picked one is unsafe too)."""
    payload = build_filler_request(
        model, utterance, lookup, history, avoid, topic, care, language, guest
    )
    started = time.perf_counter()

    def note(text: str) -> None:
        if on_event is not None:
            on_event(f"filler: {text}")

    note(f"asking {model} for a line")
    try:
        response = await asyncio.wait_for(
            client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            ),
            timeout_s,
        )
        response.raise_for_status()
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        usage = body.get("usage") or {}
        cost = usage.get("cost")
        usage_logger.info(
            "Filler %s: %s input tokens, %s output, $%s, %dms",
            body.get("model") or model,
            usage.get("prompt_tokens", "?"),
            usage.get("completion_tokens", "?"),
            f"{cost:.6f}" if isinstance(cost, (int, float)) else "?",
            (time.perf_counter() - started) * 1000,
        )
        text = json.loads(content)["text"]
    except (TimeoutError, asyncio.TimeoutError):
        logger.info("filler timed out after %.2fs", timeout_s)
        note(f"{model} timed out after {timeout_s:.2f} s, no line")
        return None
    except Exception as exc:
        logger.warning("filler failed: %s", exc)
        note(f"{model} failed ({exc}), no line")
        return None
    took = time.perf_counter() - started
    max_words = CARE_FILLER_MAX_WORDS if care else FILLER_MAX_WORDS
    line = safe_filler(text, utterance, max_words) if isinstance(text, str) else None
    if line is not None and not reply_language.fits(line, language):
        line = None
    if line is None:
        logger.info("filler dropped: %r", text)
        note(f'{model} wrote "{text}" in {took:.2f} s, dropped (unsafe or too long)')
    else:
        note(f'{model} wrote "{line}" in {took:.2f} s')
    return line
