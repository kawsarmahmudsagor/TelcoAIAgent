import uuid

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.telco import Subscriber
from app.services.auth_service import decode_access_token

__all__ = ["get_db", "get_current_admin", "get_current_subscriber", "PORTAL_COOKIE"]

PORTAL_COOKIE = "portal_session"


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
