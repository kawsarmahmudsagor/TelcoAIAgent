from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete

from app.bss import monitor
from app.models.conversation import Conversation, ConversationMessage

# Far in the future so rows already in the dev database fall outside the window.
BASE = datetime.now(timezone.utc) + timedelta(days=3650)
SINCE = BASE - timedelta(hours=1)


@pytest.fixture
def convs(db):
    made: list[Conversation] = []

    def make(msgs, started=BASE):
        """msgs: (role, offset_seconds[, tool_name]) in order."""
        c = Conversation(channel="browser", started_at=started)
        db.add(c)
        db.flush()
        for seq, (role, off, *tool) in enumerate(msgs):
            db.add(
                ConversationMessage(
                    conversation_id=c.id,
                    seq=seq,
                    role=role,
                    text=f"{role} {seq}",
                    tool_name=tool[0] if tool else None,
                    created_at=started + timedelta(seconds=off),
                )
            )
        db.commit()
        made.append(c)
        return c

    yield make
    db.rollback()
    db.execute(delete(Conversation).where(Conversation.id.in_([c.id for c in made])))
    db.commit()


def test_fallback_rate_counts_turns_without_tools(db, convs):
    convs(
        [
            ("user", 0), ("tool", 1, "get_account_summary"), ("assistant", 2),
            ("user", 10), ("tool", 11, "search_packages"), ("assistant", 12),
            ("user", 20), ("tool", 21, "get_case_status"), ("assistant", 22),
            ("user", 30), ("assistant", 31),
        ]
    )
    m = monitor.metrics(db, since=SINCE)
    assert m["turns"] == 4
    assert m["fallback_rate"] == 0.25


def test_first_response_median_and_p95(db, convs):
    msgs = []
    for i, gap in enumerate([1, 2, 3, 10]):
        msgs += [("user", i * 100), ("assistant", i * 100 + gap)]
    convs(msgs)
    m = monitor.metrics(db, since=SINCE)
    assert m["median_first_response_s"] == 2.5
    assert 3 <= m["p95_first_response_s"] <= 10


def test_resolution_rate_excludes_handoffs(db, convs):
    for _ in range(3):
        convs([("user", 0), ("assistant", 1)])
    convs([("user", 0), ("tool", 1, "request_human_agent"), ("assistant", 2)])
    m = monitor.metrics(db, since=SINCE)
    assert m["chats"] == 4
    assert m["resolution_rate"] == 0.75


def test_intents_group_tools(db, convs):
    convs(
        [
            ("user", 0), ("tool", 1, "get_account_summary"), ("tool", 2, "get_usage_breakdown"),
            ("tool", 3, "verify_otp"), ("assistant", 4),
            ("user", 10), ("tool", 11, "get_account_summary"), ("assistant", 12),
        ]
    )
    intents = monitor.metrics(db, since=SINCE)["intents"]
    assert intents == [{"label": "Balance & usage", "count": 3, "share": 1.0}]


def test_empty_window_has_no_samples(db):
    m = monitor.metrics(db, since=datetime.now(timezone.utc) + timedelta(days=36000))
    assert m["chats"] == 0
    assert m["fallback_rate"] == 0.0
    assert m["resolution_rate"] == 0.0
    assert m["median_first_response_s"] is None
    assert m["p95_first_response_s"] is None
    assert m["intents"] == []


def test_review_queue_needs_two_no_tool_turns(db, convs):
    flagged = convs([("user", 0), ("assistant", 1), ("user", 10), ("assistant", 11)])
    convs([("user", 0), ("assistant", 1), ("user", 10), ("tool", 11, "search_packages")])
    q = monitor.review_queue(db, since=SINCE)
    assert [r["conversation_id"] for r in q] == [flagged.id]
    assert q[0]["no_tool_turns"] == 2
