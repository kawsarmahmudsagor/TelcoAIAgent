import uuid

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db
from app.models.telco import Subscriber
from app.services.auth_service import create_access_token, decode_access_token

__all__ = [
    "get_db",
    "get_current_admin",
    "get_current_subscriber",
    "get_optional_subscriber",
    "PORTAL_COOKIE",
    "set_portal_session",
]

PORTAL_COOKIE = "portal_session"


def set_portal_session(response: Response, subscriber_id: uuid.UUID) -> None:
    """Sign the response's browser in as this customer."""
    response.set_cookie(
        PORTAL_COOKIE,
        create_access_token(str(subscriber_id), "customer"),
        httponly=True,
        samesite="lax",
        secure=False,  # set True once served over HTTPS
        max_age=get_settings().jwt_expire_minutes * 60,
    )


def get_current_admin(request: Request) -> str:
    token = request.cookies.get("session")
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    claims = decode_access_token(token)
    if claims is None or claims.role != "admin":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")
    return claims.sub


def get_current_subscriber(request: Request, db: Session = Depends(get_db)) -> uuid.UUID:
    """The subscriber of a valid customer `portal_session` token."""
    token = request.cookies.get(PORTAL_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    claims = decode_access_token(token)
    if claims is None or claims.role != "customer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")
    try:
        subscriber_id = uuid.UUID(claims.sub)
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")
    if db.get(Subscriber, subscriber_id) is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")
    return subscriber_id


def get_optional_subscriber(request: Request, db: Session = Depends(get_db)) -> uuid.UUID | None:
    """The logged-in subscriber, or None for a guest (no cookie, or one that doesn't verify)."""
    try:
        return get_current_subscriber(request, db)
    except HTTPException:
        return None
