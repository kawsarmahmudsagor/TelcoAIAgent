"""When the reply offers more help ("আর কিছু জানতে চান?"), the way a person on
a helpline does: when the customer closes the topic (accepts the answer,
thanks, says what they'll do), not while they're asking follow-ups.

The turn judge decides that for each accepted turn (turn_judge's wrap-up
question) and the turn sets userdata.wrap_up; a turn the judge didn't see
falls back to acknowledges(). A finished purchase or recharge asks for the
offer in its own tool result (app.agent.actions), and silence gets the idle
check-in. As a backstop, five answers in a row without a question get a
reminder too. The model words the offer itself; the reminder goes last in a
copy of its context, after the customer's message and any tool results.
"""

import re
import unicodedata

from livekit.agents import llm

from app.agent import turn_gate

# Replies in a row ending without a question before the backstop reminder.
_BACKSTOP = 5
# P(closing the topic) from the judge that counts as closing.
WRAP_UP_P = 0.5

WRAP_UP_REMINDER = (
    "The customer is closing this topic (accepting your answer, thanking you or saying what "
    "they'll do). Reply briefly, then ask whether they need help with anything else, in short "
    "words different from any offer you've made, in the language of their message."
)
BACKSTOP_REMINDER = (
    "Your last few replies ended without a question or an offer of more help. If your reply "
    "to this message answers what they asked, end it with one short offer of more help, "
    "worded differently from any you've used, in the language of their message."
)

# A short turn that only acknowledges: what the judge would say, for a turn
# it didn't see ("ঠিক আছে" may be accepted without a judge call).
_ACK_RE = re.compile(
    unicodedata.normalize(
        "NFC",
        r"^\W*(?:(?:জি|হুম|হ্যাঁ|আচ্ছা|ঠিক\s*আছে|ওকে|বুঝেছি|বুঝলাম|বুঝতে\s*পেরেছি|ধন্যবাদ|থ্যাংক\s*ইউ|"
        r"থ্যাংকস|ok(?:ay)?|got\s+it|i\s+see|understood|thanks?(?:\s+you)?|alright|fine|great)"
        r"[\s,।.!]*){1,4}$",
    ),
    re.IGNORECASE,
)


def acknowledges(text: str) -> bool:
    return bool(_ACK_RE.match(unicodedata.normalize("NFC", text or "").strip()))


def wraps_up(wrap_up_p: float | None, text: str) -> bool:
    """The judge's answer when it gave one, else the acknowledgement words.
    Never for thanks, bye or "আর লাগবে না" (turn_gate.is_closing): the goodbye
    handling owns those, asking "anything else?" after a bare thanks and
    saying goodbye after a no, not offering more help again."""
    if turn_gate.is_closing(text):
        return False
    if wrap_up_p is not None:
        return wrap_up_p >= WRAP_UP_P
    return acknowledges(text)


def _assistant_replies(chat_ctx: llm.ChatContext) -> list[str]:
    return [
        text
        for item in chat_ctx.items
        if getattr(item, "type", None) == "message" and item.role == "assistant"
        and (text := (item.text_content or "").strip())
    ]


def reminder(chat_ctx: llm.ChatContext, userdata: object) -> str | None:
    """The reminder this reply gets, or None. None while a code or a yes/no is
    awaited: the next reply is about that."""
    if getattr(userdata, "pending_action", None) or getattr(userdata, "pending_case", None):
        return None
    if getattr(userdata, "wrap_up", False):
        return WRAP_UP_REMINDER
    replies = _assistant_replies(chat_ctx)[-_BACKSTOP:]
    if len(replies) == _BACKSTOP and not any(r.endswith(("?", "？")) for r in replies):
        return BACKSTOP_REMINDER
    return None


def with_reminder(chat_ctx: llm.ChatContext, userdata: object) -> llm.ChatContext:
    """The context the main model gets for this step: with the reminder last,
    when one is due (the model barely heeds a note placed before the
    customer's message). A copy: the session's history never keeps it."""
    note = reminder(chat_ctx, userdata)
    if note is None:
        return chat_ctx
    chat_ctx = chat_ctx.copy()
    chat_ctx.add_message(role="system", content=note)
    return chat_ctx
