from fastapi import HTTPException, Request, status

from app.db.session import get_db
from app.services.auth_service import decode_access_token

__all__ = ["get_db", "get_current_admin"]


def get_current_admin(request: Request) -> str:
    token = request.cookies.get("session")
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    username = decode_access_token(token)
    if not username:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")
    return username
