"""Unauthenticated: the public chat widget's "recent conversations" list.

A browser is identified only by its anonymous visitor id -- a random UUID it
keeps in localStorage and passes to the agent (via the token route's dispatch
metadata), which stores it on the conversation row. The id is a bearer-like
secret: it travels in the X-Visitor-Id header (not the query string, so it
stays out of access logs), nothing is listed without it, a conversation of
another visitor is a plain 404, and phone-call conversations are never
returned. A logged-in customer (a valid `portal_session` cookie) also sees
their own chats from other browsers. Responses carry no internal fields (room,
client, schedule ids)."""

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_optional_subscriber
from app.api.routes_conversations import _preview
from app.repositories import conversation_repo
from app.schemas.conversation import (
    VisitorConversationDetail,
    VisitorConversationMessage,
    VisitorConversationPage,
    VisitorConversationSummary,
)

router = APIRouter(prefix="/api/public/conversations", tags=["public"])

MAX_PAGE = 20
_NO_STORE = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}


def visitor_id_header(x_visitor_id: uuid.UUID = Header(...)) -> uuid.UUID:
    """The caller's visitor id; a missing or malformed one is a 422."""
    return x_visitor_id


@router.get("", response_model=VisitorConversationPage)
def list_visitor_conversations(
    response: Response,
    visitor_id: uuid.UUID = Depends(visitor_id_header),
    subscriber_id: uuid.UUID | None = Depends(get_optional_subscriber),
    db: Session = Depends(get_db),
    limit: int = Query(default=3, ge=1, le=MAX_PAGE),
    offset: int = Query(default=0, ge=0),
    # The browser's current room: that session is live in the panel already.
    exclude_room: str | None = Query(default=None, max_length=255),
) -> VisitorConversationPage:
    response.headers.update(_NO_STORE)
    rows, total = conversation_repo.list_for_visitor(
        db,
        visitor_id,
        limit=limit,
        offset=offset,
        exclude_room=exclude_room,
        subscriber_id=subscriber_id,
    )
    return VisitorConversationPage(
        items=[
            VisitorConversationSummary(
                id=conversation.id,
                started_at=conversation.started_at,
                ended_at=conversation.ended_at,
                status=conversation.status,
                preview=_preview(first_message),
                message_count=count or 0,
                reply_language=conversation.reply_language,
            )
            for conversation, first_message, count in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


# A plain str rather than uuid.UUID: a malformed id is just a conversation that
# doesn't exist (404).
@router.get("/{conversation_id}", response_model=VisitorConversationDetail)
def get_visitor_conversation(
    conversation_id: str,
    response: Response,
    visitor_id: uuid.UUID = Depends(visitor_id_header),
    subscriber_id: uuid.UUID | None = Depends(get_optional_subscriber),
    db: Session = Depends(get_db),
) -> VisitorConversationDetail:
    response.headers.update(_NO_STORE)
    try:
        parsed = uuid.UUID(conversation_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="conversation not found") from None
    conversation = conversation_repo.get_for_visitor(
        db, visitor_id, parsed, subscriber_id=subscriber_id
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    messages = conversation_repo.list_visible_messages(db, conversation.id)
    return VisitorConversationDetail(
        id=conversation.id,
        started_at=conversation.started_at,
        ended_at=conversation.ended_at,
        status=conversation.status,
        reply_language=conversation.reply_language,
        messages=[VisitorConversationMessage.model_validate(m) for m in messages],
    )
