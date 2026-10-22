import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TimestampedBase


class ConversationStatus(str, enum.Enum):
    active = "active"
    ended = "ended"


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    tool = "tool"


class Conversation(TimestampedBase):
    """One agent session (browser chat/voice or phone call).

    Written by app.agent.transcript.TranscriptRecorder. updated_at doubles as
    "last activity": every stored message bumps it, and the scheduler's stale
    sweep ends conversations whose worker died without closing them."""

    __tablename__ = "conversations"

    # app.agent.userdata.Channel values -- plain string, not a new enum.
    channel: Mapped[str] = mapped_column(String(32), index=True)
    room_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # The subscriber the session was about, set when the recorder closes it.
    subscriber_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subscribers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_phone_call: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # The browser's anonymous visitor id (a UUID it keeps in localStorage), for
    # the chat widget's "recent conversations" list. Browser chats only; it is a
    # bearer-like secret, so it is never returned by any API response.
    visitor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(
        String(16), default=ConversationStatus.active.value, server_default="active", index=True
    )
    message_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ConversationMessage(TimestampedBase):
    __tablename__ = "conversation_messages"
    __table_args__ = (UniqueConstraint("conversation_id", "seq", name="uq_conversation_message_seq"),)

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    # Order the recorder received the items in; created_at is the item's own time.
    seq: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16))
    # Message text, or a short tool output for role=tool.
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tool_args: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
