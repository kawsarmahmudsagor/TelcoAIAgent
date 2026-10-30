import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_db
from app.models.conversation import ConversationStatus
from app.models.telco import Subscriber
from app.repositories import conversation_repo
from app.services import conversation_export
from app.services.conversation_export import ConversationStillActive, ExportTranslationError
from app.schemas.conversation import (
    BulkDeleteRequest,
    BulkDeleteResult,
    ConversationDetail,
    ConversationListItem,
    ConversationMessageOut,
    ConversationOut,
    ConversationPage,
)

router = APIRouter(
    prefix="/api/conversations",
    tags=["conversations"],
    dependencies=[Depends(get_current_admin)],
)

PREVIEW_MAX_CHARS = 140
# app.agent.userdata.Channel values (not imported: it pulls in livekit.rtc).
ChannelLiteral = Literal["inbound_chat"]


def _preview(text: str | None) -> str | None:
    if text is None or len(text) <= PREVIEW_MAX_CHARS:
        return text
    return text[: PREVIEW_MAX_CHARS - 1] + "…"


def list_items(rows) -> list[ConversationListItem]:
    return [
        ConversationListItem(
            **ConversationOut.model_validate(conversation).model_dump(),
            subscriber_name=subscriber_name,
            preview=_preview(first_message),
        )
        for conversation, subscriber_name, first_message in rows
    ]


@router.get("", response_model=ConversationPage)
def list_conversations(
    db: Session = Depends(get_db),
    channel: ChannelLiteral | None = None,
    conversation_status: ConversationStatus | None = Query(default=None, alias="status"),
    subscriber_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ConversationPage:
    rows, total = conversation_repo.list_page(
        db,
        channel=channel,
        status=conversation_status.value if conversation_status else None,
        subscriber_id=subscriber_id,
        limit=limit,
        offset=offset,
    )
    return ConversationPage(items=list_items(rows), total=total, limit=limit, offset=offset)


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: uuid.UUID, db: Session = Depends(get_db)) -> ConversationDetail:
    conversation = conversation_repo.get(db, conversation_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    messages = conversation_repo.list_messages(db, conversation_id)
    subscriber = (
        db.get(Subscriber, conversation.subscriber_id) if conversation.subscriber_id else None
    )
    return ConversationDetail(
        **ConversationOut.model_validate(conversation).model_dump(),
        subscriber_name=subscriber.full_name if subscriber else None,
        messages=[ConversationMessageOut.model_validate(message) for message in messages],
    )


def export_response(
    db: Session, conversation, lang, headers: dict[str, str] | None = None
) -> Response:
    """The conversation as a .docx download; 409 while live, 502 when translation fails."""
    try:
        filename, content = conversation_export.export_conversation(db, conversation, lang)
    except ConversationStillActive:
        raise HTTPException(status.HTTP_409_CONFLICT, "conversation is still active") from None
    except ExportTranslationError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "translation failed") from None
    return Response(
        content,
        media_type=conversation_export.MEDIA_TYPE,
        headers={**(headers or {}), "Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{conversation_id}/export")
def export_conversation(
    conversation_id: uuid.UUID,
    lang: Literal["en", "bn"],
    db: Session = Depends(get_db),
) -> Response:
    conversation = conversation_repo.get(db, conversation_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return export_response(db, conversation, lang)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    if not conversation_repo.delete_many(db, [conversation_id]):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/bulk-delete", response_model=BulkDeleteResult)
def bulk_delete_conversations(
    payload: BulkDeleteRequest, db: Session = Depends(get_db)
) -> BulkDeleteResult:
    return BulkDeleteResult(deleted=conversation_repo.delete_many(db, list(set(payload.ids))))
