import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    channel: str
    room_name: str | None
    client_id: uuid.UUID | None
    call_schedule_id: uuid.UUID | None
    is_phone_call: bool
    status: str
    message_count: int
    started_at: datetime
    ended_at: datetime | None


class ConversationListItem(ConversationOut):
    client_name: str | None = None
    # First thing the customer said, trimmed.
    preview: str | None = None


class ConversationPage(BaseModel):
    items: list[ConversationListItem]
    total: int
    limit: int
    offset: int


class ConversationMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    seq: int
    role: str
    text: str | None
    tool_name: str | None
    tool_args: dict | None
    created_at: datetime


class ConversationDetail(ConversationOut):
    client_name: str | None = None
    client_email: str | None = None
    client_phone: str | None = None
    messages: list[ConversationMessageOut]


class BulkDeleteRequest(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


class BulkDeleteResult(BaseModel):
    deleted: int


# --- public: the chat widget's "recent conversations" (no internal fields) --------


class VisitorConversationSummary(BaseModel):
    id: uuid.UUID
    started_at: datetime
    ended_at: datetime | None
    status: str
    # First thing the customer said, trimmed -- the list's title.
    preview: str | None
    # User + assistant messages (tool rows aren't shown to the visitor).
    message_count: int


class VisitorConversationPage(BaseModel):
    items: list[VisitorConversationSummary]
    total: int
    limit: int
    offset: int


class VisitorConversationMessage(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seq: int
    role: str
    text: str | None
    created_at: datetime


class VisitorConversationDetail(BaseModel):
    id: uuid.UUID
    started_at: datetime
    ended_at: datetime | None
    status: str
    messages: list[VisitorConversationMessage]
