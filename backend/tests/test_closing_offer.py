"""When the reply offers more help (app.agent.closing_offer)."""

from types import SimpleNamespace

import pytest
from livekit.agents import llm

from app.agent import closing_offer


def _ctx(*replies: str) -> llm.ChatContext:
    ctx = llm.ChatContext.empty()
    for reply in replies:
        ctx.add_message(role="user", content="প্রশ্ন")
        ctx.add_message(role="assistant", content=reply)
    ctx.add_message(role="user", content="এছাড়া কি আর কিছু করা লাগবে?")
    return ctx


def _ud(*, wrap_up=False, pending_action=None, pending_case=None):
    return SimpleNamespace(wrap_up=wrap_up, pending_action=pending_action, pending_case=pending_case)


def test_closing_the_topic_gets_the_offer_reminder_last():
    ctx = _ctx("অরিজিনাল এনআইডি কার্ডটাই আনবেন।")
    sent = closing_offer.with_reminder(ctx, _ud(wrap_up=True))
    assert sent.items[-1].role == "system"
    assert sent.items[-1].text_content == closing_offer.WRAP_UP_REMINDER
    # A copy: the session's own context is untouched.
    assert ctx.items[-1].role == "user"


def test_follow_ups_get_no_reminder_until_the_backstop():
    # From a call: follow-ups on a lost SIM. Mid-topic, no offer after each answer.
    answers = [f"উত্তর {i}।" for i in range(5)]
    for n in range(1, 5):
        assert closing_offer.reminder(_ctx(*answers[:n]), _ud()) is None
    assert closing_offer.reminder(_ctx(*answers), _ud()) == closing_offer.BACKSTOP_REMINDER
    with_question = [*answers[:4], "আর কিছু জানতে চান?"]
    assert closing_offer.reminder(_ctx(*with_question), _ud()) is None


@pytest.mark.parametrize("pending", ["pending_action", "pending_case"])
def test_no_reminder_while_a_code_or_a_case_is_awaited(pending):
    ud = _ud(wrap_up=True, **{pending: object()})
    assert closing_offer.reminder(_ctx(*(["ঠিক আছে।"] * 5)), ud) is None


@pytest.mark.parametrize(
    ("wrap_up_p", "text", "expected"),
    [
        (0.9, "হুম, বুঝলাম, ওটাই করব তাহলে", True),
        (0.1, "ঠিক আছে", False),  # the judge's answer wins
        (None, "আচ্ছা, বুঝেছি", True),  # no judge answer: the words
        # Thanks, bye or "no more" belong to the goodbye handling.
        (0.86, "না, আর লাগবে না", False),
        (0.91, "অনেক ধন্যবাদ", False),
        (None, "ok thanks", False),
        (None, "ঠিক আছে", True),
        (None, "ঠিক আছে, ফি কত?", False),
        (None, "এছাড়া কি আর কিছু করা লাগবে?", False),
    ],
)
def test_wraps_up(wrap_up_p, text, expected):
    assert closing_offer.wraps_up(wrap_up_p, text) is expected
