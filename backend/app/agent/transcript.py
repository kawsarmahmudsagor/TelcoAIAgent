"""Stores each session's transcript in `conversations` / `conversation_messages`.

LiveKit's `session.on` rejects async callbacks, so the handlers are sync: they
only number each item and push it onto an asyncio.Queue. A single writer task
drains the queue with `to_thread` inserts, which keeps rows in the order the
items arrived (`seq`) without blocking the event loop on the database.
"""

import asyncio
import json
import logging
import uuid
from collections import OrderedDict, deque
from datetime import datetime, timezone
from typing import Any

from app.agent.userdata import SessionUserdata
from app.db.session import SessionLocal
from app.models.conversation import MessageRole
from app.repositories import conversation_repo

logger = logging.getLogger("agent.transcript")

# Tool outputs can be long (a whole search result); the transcript keeps a gist.
TOOL_OUTPUT_MAX_CHARS = 500
_STORED_ROLES = {MessageRole.user.value, MessageRole.assistant.value}
_STOP = object()
# Rows stored after a user message are kept in this order: what the agent said
# while working (a filler line), then the lookups that ran before its reply.
FILLER_ROW, TOOL_ROW = 0, 1
# Turns whose rows may wait for their user message: a reply that is dropped
# never adds it, so older ones are forgotten.
_PENDING_TURNS = 16


def _to_datetime(ts: float | None) -> datetime:
    if ts is None:
        return datetime.now(timezone.utc)
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _parse_args(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {"raw": raw}
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def _short(text: str | None) -> str | None:
    if text is None:
        return None
    if len(text) <= TOOL_OUTPUT_MAX_CHARS:
        return text
    return text[: TOOL_OUTPUT_MAX_CHARS - 1] + "…"


def _insert(conversation_id: uuid.UUID, row: dict[str, Any]) -> None:
    db = SessionLocal()
    try:
        conversation_repo.add_message(db, conversation_id, **row)
    finally:
        db.close()


def _finish(conversation_id: uuid.UUID, client_id: uuid.UUID | None) -> None:
    db = SessionLocal()
    try:
        conversation_repo.end(db, conversation_id, client_id=client_id)
    finally:
        db.close()


def create_conversation(userdata: SessionUserdata, room_name: str | None) -> uuid.UUID:
    db = SessionLocal()
    try:
        # TODO(Task 4): the column becomes subscriber_id; pass userdata.subscriber_id then.
        conversation = conversation_repo.create(
            db,
            channel=userdata.channel.value,
            room_name=room_name,
            client_id=None,
            is_phone_call=userdata.is_phone_call,
            visitor_id=getattr(userdata, "visitor_id", None),
        )
        return conversation.id
    finally:
        db.close()


class TranscriptRecorder:
    def __init__(self, conversation_id: uuid.UUID, userdata: SessionUserdata) -> None:
        self.conversation_id = conversation_id
        self._userdata = userdata
        self._queue: asyncio.Queue = asyncio.Queue()
        self._seq = 0
        self._closed = False
        self._writer: asyncio.Task | None = None
        # message id -> (order, row) waiting for that user message (after_user).
        self._pending: OrderedDict[str, list[tuple[int, dict[str, Any]]]] = OrderedDict()
        self._users_seen: deque[str] = deque(maxlen=_PENDING_TURNS)

    @classmethod
    async def start(
        cls, session, userdata: SessionUserdata, room_name: str | None
    ) -> "TranscriptRecorder | None":
        """Creates the conversation row and subscribes to `session`. Returns None
        (and logs) if the row can't be created -- a transcript problem must
        never take the call down with it."""
        try:
            conversation_id = await asyncio.to_thread(create_conversation, userdata, room_name)
        except Exception:
            logger.exception("could not create the conversation row; transcript disabled")
            return None
        userdata.conversation_id = conversation_id
        recorder = cls(conversation_id, userdata)
        recorder.attach(session)
        return recorder

    def attach(self, session) -> None:
        session.on("conversation_item_added", self.on_conversation_item_added)
        session.on("function_tools_executed", self.on_function_tools_executed)
        self._ensure_writer()

    def _ensure_writer(self) -> None:
        if self._writer is None:
            self._writer = asyncio.get_running_loop().create_task(self._drain())

    # --- sync event handlers -----------------------------------------------------

    def on_conversation_item_added(self, event) -> None:
        item = event.item
        # Skips AgentHandoff / config-update items and system/developer messages.
        if getattr(item, "type", None) != "message" or item.role not in _STORED_ROLES:
            return
        text = (item.text_content or "").strip()
        if text:
            self._push(
                {
                    "role": item.role,
                    "text": text,
                    "created_at": _to_datetime(getattr(item, "created_at", None)),
                }
            )
        if item.role == MessageRole.user.value and (item_id := getattr(item, "id", None)):
            self._users_seen.append(item_id)
            for _order, row in sorted(self._pending.pop(item_id, []), key=lambda entry: entry[0]):
                self._push(row)

    def on_function_tools_executed(self, event) -> None:
        for call, output in event.zipped():
            self._push(
                {
                    "role": MessageRole.tool.value,
                    "text": _short(output.output if output is not None else None),
                    "tool_name": call.name,
                    "tool_args": _parse_args(call.arguments),
                    "created_at": _to_datetime(getattr(call, "created_at", None)),
                }
            )

    def record_tool(self, name: str, args: dict | None, output: str | None) -> None:
        """A tool row for work done outside the LLM's tool calls."""
        self._push(
            {
                "role": MessageRole.tool.value,
                "text": _short(output),
                "tool_name": name,
                "tool_args": args,
                "created_at": datetime.now(timezone.utc),
            }
        )

    def record_tool_after(
        self, message_id: str, name: str, args: dict | None, output: str | None
    ) -> None:
        """A lookup run before the LLM for user message `message_id`
        (app.agent.prefetch), stored right after that message."""
        row = {
            "role": MessageRole.tool.value,
            "text": _short(output),
            "tool_name": name,
            "tool_args": args,
            "created_at": datetime.now(timezone.utc),
        }
        self.after_user(message_id, TOOL_ROW, row)

    def record_assistant_after(self, message_id: str, text: str) -> None:
        """A line the agent said outside the chat context (a quick-reply filler)
        while answering user message `message_id`, stored right after it."""
        row = {"role": MessageRole.assistant.value, "text": text, "created_at": datetime.now(timezone.utc)}
        self.after_user(message_id, FILLER_ROW, row)

    def after_user(self, message_id: str, order: int, row: dict[str, Any]) -> None:
        """Stores `row` after user message `message_id`: now if that message is
        already stored, else once it is. Session handlers run in no set order,
        so the user message may reach this recorder before or after the code
        that made the row; either way the rows land after it, by `order`. A
        message that is never added (its reply was dropped) takes its rows
        with it."""
        if message_id in self._users_seen:
            self._push(row)
            return
        self._pending.setdefault(message_id, []).append((order, row))
        while len(self._pending) > _PENDING_TURNS:
            self._pending.popitem(last=False)

    def _push(self, row: dict[str, Any]) -> None:
        if self._closed:
            logger.warning("transcript item after close dropped (conversation %s)", self.conversation_id)
            return
        self._seq += 1
        row["seq"] = self._seq
        self._queue.put_nowait(row)

    # --- writer ------------------------------------------------------------------

    async def _drain(self) -> None:
        while True:
            row = await self._queue.get()
            if row is _STOP:
                return
            try:
                await asyncio.to_thread(_insert, self.conversation_id, row)
            except Exception:
                logger.exception(
                    "could not store transcript item %s of conversation %s",
                    row.get("seq"),
                    self.conversation_id,
                )

    async def close(self) -> None:
        """Drains every queued item, then marks the conversation ended and links
        it to the lead found during the session. Safe to call more than once."""
        if self._closed:
            return
        self._closed = True
        self._pending.clear()
        self._queue.put_nowait(_STOP)
        if self._writer is not None:
            await self._writer
        userdata = self._userdata
        # TODO(Task 4): store userdata.subscriber_id once the column is renamed.
        try:
            await asyncio.to_thread(_finish, self.conversation_id, None)
        except Exception:
            logger.exception("could not mark conversation %s ended", self.conversation_id)
