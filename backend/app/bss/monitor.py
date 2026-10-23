"""AI monitor: what the agent did, derived from stored conversations and the audit trail."""

import math
import uuid
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.bss.accounts import mask_msisdn
from app.models.conversation import Conversation, ConversationMessage, MessageRole
from app.models.telco import AuditEvent, Subscriber

TOOL_INTENT: dict[str, str] = {
    "get_account_summary": "Balance & usage",
    "get_usage_breakdown": "Balance & usage",
    "explain_deductions": "Balance & usage",
    "search_packages": "Packages",
    "recommend_packages": "Packages",
    "purchase_package": "Packages",
    "start_recharge": "Recharge",
    "lookup_transactions": "Recharge",
    "get_offers_and_points": "Offers & rewards",
    "redeem_reward": "Offers & rewards",
    "create_support_case": "Support",
    "get_case_status": "Support",
    "request_human_agent": "Support",
    "check_network_status": "Network",
    "search_knowledge_base": "Knowledge base",
}

_PREVIEW_CHARS = 140
_Turn = tuple[ConversationMessage, list[ConversationMessage]]


def _messages_since(db: Session, since: datetime) -> dict[uuid.UUID, list[ConversationMessage]]:
    rows = db.scalars(
        select(ConversationMessage)
        .where(ConversationMessage.created_at >= since)
        .order_by(ConversationMessage.conversation_id, ConversationMessage.seq)
    )
    by_conv: dict[uuid.UUID, list[ConversationMessage]] = defaultdict(list)
    for m in rows:
        by_conv[m.conversation_id].append(m)
    return by_conv


def _turns(msgs: list[ConversationMessage]) -> list[_Turn]:
    """Each user message with the messages after it, up to the next user message."""
    turns: list[_Turn] = []
    for m in msgs:
        if m.role == MessageRole.user.value:
            turns.append((m, []))
        elif turns:
            turns[-1][1].append(m)
    return turns


def _no_tool(following: list[ConversationMessage]) -> bool:
    return not any(m.role == MessageRole.tool.value for m in following)


def _percentile(sorted_samples: list[float], p: float) -> float:
    """Nearest-rank percentile."""
    rank = max(1, math.ceil(p / 100 * len(sorted_samples)))
    return sorted_samples[rank - 1]


def _median(sorted_samples: list[float]) -> float:
    mid = len(sorted_samples) // 2
    if len(sorted_samples) % 2:
        return sorted_samples[mid]
    return (sorted_samples[mid - 1] + sorted_samples[mid]) / 2


def metrics(db: Session, *, since: datetime) -> dict[str, Any]:
    chats = db.scalars(select(Conversation.id).where(Conversation.started_at >= since)).all()
    by_conv = _messages_since(db, since)

    turn_count = 0
    no_tool_turns = 0
    latencies: list[float] = []
    intents: Counter[str] = Counter()
    for msgs in by_conv.values():
        for user_msg, following in _turns(msgs):
            turn_count += 1
            if _no_tool(following):
                no_tool_turns += 1
            reply = next((m for m in following if m.role == MessageRole.assistant.value), None)
            if reply is not None:
                latencies.append((reply.created_at - user_msg.created_at).total_seconds())
        for m in msgs:
            if m.role == MessageRole.tool.value and m.tool_name in TOOL_INTENT:
                intents[TOOL_INTENT[m.tool_name]] += 1

    handoffs = sum(
        1
        for cid in chats
        if any(m.tool_name == "request_human_agent" for m in by_conv.get(cid, []))
    )
    latencies.sort()
    total_intents = sum(intents.values())
    return {
        "chats": len(chats),
        "turns": turn_count,
        "fallback_rate": no_tool_turns / turn_count if turn_count else 0.0,
        "resolution_rate": (len(chats) - handoffs) / len(chats) if chats else 0.0,
        "median_first_response_s": _median(latencies) if latencies else None,
        "p95_first_response_s": _percentile(latencies, 95) if latencies else None,
        "intents": [
            {"label": label, "count": n, "share": n / total_intents}
            for label, n in sorted(intents.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
    }


def review_queue(db: Session, *, since: datetime, limit: int = 5) -> list[dict[str, Any]]:
    convs = db.execute(
        select(Conversation, Subscriber.full_name)
        .outerjoin(Subscriber, Subscriber.id == Conversation.subscriber_id)
        .where(Conversation.started_at >= since)
        .order_by(Conversation.started_at.desc())
    ).all()
    by_conv = _messages_since(db, since)
    out: list[dict[str, Any]] = []
    for conv, name in convs:
        flagged = [u for u, following in _turns(by_conv.get(conv.id, [])) if _no_tool(following)]
        if len(flagged) < 2:
            continue
        out.append(
            {
                "conversation_id": conv.id,
                "started_at": conv.started_at,
                "subscriber_name": name,
                "no_tool_turns": len(flagged),
                "preview": (flagged[0].text or "")[:_PREVIEW_CHARS],
            }
        )
        if len(out) >= limit:
            break
    return out


def audit_trail(db: Session, *, limit: int = 50) -> list[dict[str, Any]]:
    rows = db.execute(
        select(AuditEvent, Subscriber.full_name, Subscriber.msisdn)
        .outerjoin(Subscriber, Subscriber.id == AuditEvent.subscriber_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "created_at": e.created_at,
            "actor": e.actor.value,
            "action": e.action,
            "subscriber_name": name,
            "msisdn_masked": mask_msisdn(msisdn) if msisdn else None,
            "detail": ", ".join(f"{k}: {v}" for k, v in (e.detail or {}).items()),
        }
        for e, name, msisdn in rows
    ]
