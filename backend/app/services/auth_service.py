from datetime import datetime, timedelta, timezone
from typing import Literal

import bcrypt
from jose import JWTError, jwt
from pydantic import BaseModel

from app.config import get_settings

_JWT_ALGORITHM = "HS256"


class TokenClaims(BaseModel):
    sub: str
    role: Literal["admin", "customer"]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_admin(username: str, password: str) -> bool:
    settings = get_settings()
    if username != settings.admin_username:
        return False
    if not settings.admin_password_hash:
        return False
    return bcrypt.checkpw(password.encode(), settings.admin_password_hash.encode())


def create_access_token(sub: str, role: Literal["admin", "customer"] = "admin") -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": sub, "role": role, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=_JWT_ALGORITHM)


def decode_access_token(token: str) -> TokenClaims | None:
    """Claims of a valid token; a token without `role` counts as admin."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[_JWT_ALGORITHM])
    except JWTError:
        return None
    sub = payload.get("sub")
    role = payload.get("role", "admin")
    if not isinstance(sub, str) or not sub or role not in ("admin", "customer"):
        return None
    return TokenClaims(sub=sub, role=role)
