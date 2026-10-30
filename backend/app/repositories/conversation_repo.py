import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import Date, cast, delete, false, func, or_, select, update
from sqlalchemy.orm import Session

from app.models.conversation import (
    Conversation,
    ConversationMessage,
    ConversationStatus,
    MessageRole,
)
from app.models.telco import Subscriber


def get(db: Session, conversation_id: uuid.UUID) -> Conversation | None:
    return db.get(Conversation, conversation_id)


def create(
    db: Session,
    *,
    channel: str,
    room_name: str | None,
    subscriber_id: uuid.UUID | None = None,
    is_phone_call: bool = False,
    visitor_id: uuid.UUID | None = None,
    reply_language: str | None = None,
) -> Conversation:
    conversation = Conversation(
        reply_language=reply_language,
        channel=channel,
        room_name=room_name,
        subscriber_id=subscriber_id,
        is_phone_call=is_phone_call,
        visitor_id=visitor_id,
        status=ConversationStatus.active.value,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def add_message(
    db: Session,
    conversation_id: uuid.UUID,
    *,
    seq: int,
    role: str,
    text: str | None,
    created_at: datetime,
    tool_name: str | None = None,
    tool_args: dict | None = None,
) -> None:
    db.add(
        ConversationMessage(
            conversation_id=conversation_id,
            seq=seq,
            role=role,
            text=text,
            tool_name=tool_name,
            tool_args=tool_args,
            created_at=created_at,
        )
    )
    # Also bumps updated_at (onupdate), which the stale sweep reads as last activity.
    db.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(message_count=Conversation.message_count + 1)
    )
    db.commit()


def end(
    db: Session, conversation_id: uuid.UUID, *, subscriber_id: uuid.UUID | None = None
) -> None:
    values: dict = {"status": ConversationStatus.ended.value, "ended_at": func.now()}
    if subscriber_id is not None:
        values["subscriber_id"] = subscriber_id
    db.execute(update(Conversation).where(Conversation.id == conversation_id).values(**values))
    db.commit()


def reopen(
    db: Session,
    conversation_id: uuid.UUID,
    *,
    room_name: str | None,
    reply_language: str | None = None,
) -> int:
    """An earlier conversation the customer picked up again in a new room: active
    again, in that room. A chat from before the language pick takes the new
    pick; one that has a language keeps it. Returns the highest message `seq`
    so far, for the recorder to number new messages after it."""
    db.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(
            status=ConversationStatus.active.value,
            ended_at=None,
            room_name=room_name,
            reply_language=func.coalesce(Conversation.reply_language, reply_language),
        )
    )
    db.commit()
    return (
        db.scalar(
            select(func.max(ConversationMessage.seq)).where(
                ConversationMessage.conversation_id == conversation_id
            )
        )
        or 0
    )


def link_subscriber(db: Session, conversation_id: uuid.UUID, subscriber_id: uuid.UUID) -> None:
    """A guest conversation whose visitor logged in: it now belongs to them."""
    db.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id, Conversation.subscriber_id.is_(None))
        .values(subscriber_id=subscriber_id)
    )
    db.commit()


def end_stale(db: Session, *, idle_for: timedelta, now: datetime | None = None) -> int:
    """Ends conversations still `active` with no activity for `idle_for` -- their
    agent worker crashed before closing them. ended_at = their last activity."""
    cutoff = (now or datetime.now(timezone.utc)) - idle_for
    result = db.execute(
        update(Conversation)
        .where(
            Conversation.status == ConversationStatus.active.value,
            Conversation.updated_at < cutoff,
        )
        .values(status=ConversationStatus.ended.value, ended_at=Conversation.updated_at)
    )
    db.commit()
    return result.rowcount or 0


def _first_user_message():
    return (
        select(ConversationMessage.text)
        .where(
            ConversationMessage.conversation_id == Conversation.id,
            ConversationMessage.role == MessageRole.user.value,
        )
        .order_by(ConversationMessage.seq)
        .limit(1)
        .correlate(Conversation)
        .scalar_subquery()
    )


def list_page(
    db: Session,
    *,
    channel: str | None = None,
    status: str | None = None,
    subscriber_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[tuple[Conversation, str | None, str | None]], int]:
    """Newest first. Rows are (conversation, subscriber's full name or None, first
    user message)."""
    filters = []
    if channel is not None:
        filters.append(Conversation.channel == channel)
    if status is not None:
        filters.append(Conversation.status == status)
    if subscriber_id is not None:
        filters.append(Conversation.subscriber_id == subscriber_id)

    total = db.scalar(select(func.count()).select_from(Conversation).where(*filters)) or 0
    stmt = (
        select(Conversation, Subscriber.full_name, _first_user_message())
        .outerjoin(Subscriber, Subscriber.id == Conversation.subscriber_id)
        .where(*filters)
        .order_by(Conversation.started_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return [tuple(row) for row in db.execute(stmt)], total


def list_messages(db: Session, conversation_id: uuid.UUID) -> list[ConversationMessage]:
    stmt = (
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conversation_id)
        .order_by(ConversationMessage.seq)
    )
    return list(db.scalars(stmt))


def delete_many(db: Session, ids: list[uuid.UUID]) -> int:
    if not ids:
        return 0
    result = db.execute(delete(Conversation).where(Conversation.id.in_(ids)))
    db.commit()
    return result.rowcount or 0


def count_started_between(db: Session, start: datetime, end: datetime) -> int:
    stmt = (
        select(func.count())
        .select_from(Conversation)
        .where(Conversation.started_at >= start, Conversation.started_at < end)
    )
    return db.scalar(stmt) or 0


def daily_counts(db: Session, start: datetime, end: datetime, tz_name: str) -> dict[date, int]:
    """Conversations started in [start, end), bucketed by local calendar day in
    `tz_name` (Postgres timezone() turns the timestamptz into local wall time)."""
    local_day = cast(func.timezone(tz_name, Conversation.started_at), Date)
    stmt = (
        select(local_day, func.count())
        .where(Conversation.started_at >= start, Conversation.started_at < end)
        .group_by(local_day)
    )
    return {day: count for day, count in db.execute(stmt)}


# --- the public chat widget's "recent conversations" ------------------------------

_VISIBLE_ROLES = (MessageRole.user.value, MessageRole.assistant.value)


def _visitor_filters(visitor_id: uuid.UUID | None, subscriber_id: uuid.UUID | None = None) -> list:
    """Chat conversations (never phone calls) a browser may list and reopen: its
    guest chats (by visitor id, no subscriber) and, with a server-verified
    `subscriber_id`, that customer's own chats from any browser. A chat that
    belongs to another account stays hidden even on the browser it ran in (a
    shared computer, a switched persona)."""
    owner = []
    if visitor_id is not None:
        owner.append((Conversation.visitor_id == visitor_id) & Conversation.subscriber_id.is_(None))
    if subscriber_id is not None:
        owner.append(Conversation.subscriber_id == subscriber_id)
    return [
        or_(false(), *owner),
        Conversation.channel == "inbound_chat",
        Conversation.is_phone_call.is_(False),
    ]


def list_for_visitor(
    db: Session,
    visitor_id: uuid.UUID,
    *,
    limit: int,
    offset: int = 0,
    exclude_room: str | None = None,
    subscriber_id: uuid.UUID | None = None,
) -> tuple[list[tuple[Conversation, str | None, int]], int]:
    """Newest first, only conversations where the customer said something (a
    greeting-only session is noise). Rows are (conversation, first user message,
    number of user + assistant messages); `exclude_room` drops the session the
    browser is in right now. `subscriber_id` widens the list as in
    _visitor_filters."""
    has_user_message = (
        select(ConversationMessage.id)
        .where(
            ConversationMessage.conversation_id == Conversation.id,
            ConversationMessage.role == MessageRole.user.value,
        )
        .exists()
    )
    filters = [*_visitor_filters(visitor_id, subscriber_id), has_user_message]
    if exclude_room:
        filters.append(
            (Conversation.room_name != exclude_room) | Conversation.room_name.is_(None)
        )
    visible_count = (
        select(func.count(ConversationMessage.id))
        .where(
            ConversationMessage.conversation_id == Conversation.id,
            ConversationMessage.role.in_(_VISIBLE_ROLES),
        )
        .correlate(Conversation)
        .scalar_subquery()
    )
    total = db.scalar(select(func.count()).select_from(Conversation).where(*filters)) or 0
    stmt = (
        select(Conversation, _first_user_message(), visible_count)
        .where(*filters)
        .order_by(Conversation.started_at.desc(), Conversation.id)
        .limit(limit)
        .offset(offset)
    )
    return [tuple(row) for row in db.execute(stmt)], total


def get_for_visitor(
    db: Session,
    visitor_id: uuid.UUID | None,
    conversation_id: uuid.UUID,
    *,
    subscriber_id: uuid.UUID | None = None,
) -> Conversation | None:
    """The conversation only if it belongs to this visitor, or to `subscriber_id`
    (else None, never a hint that it exists)."""
    stmt = select(Conversation).where(
        Conversation.id == conversation_id, *_visitor_filters(visitor_id, subscriber_id)
    )
    return db.scalars(stmt).first()


def list_visible_messages(db: Session, conversation_id: uuid.UUID) -> list[ConversationMessage]:
    """The customer's and the agent's messages in order; tool rows left out."""
    stmt = (
        select(ConversationMessage)
        .where(
            ConversationMessage.conversation_id == conversation_id,
            ConversationMessage.role.in_(_VISIBLE_ROLES),
        )
        .order_by(ConversationMessage.seq)
    )
    return list(db.scalars(stmt))
