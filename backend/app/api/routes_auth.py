from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import get_current_admin
from app.config import get_settings
from app.schemas.auth import LoginRequest, MeResponse
from app.services.auth_service import create_access_token, verify_admin

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(payload: LoginRequest, response: Response) -> dict:
    if not verify_admin(payload.username, payload.password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")

    settings = get_settings()
    token = create_access_token(payload.username)
    response.set_cookie(
        "session",
        token,
        httponly=True,
        samesite="lax",
        secure=False,  # set True once served over HTTPS
        max_age=settings.jwt_expire_minutes * 60,
    )
    return {"ok": True}


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie("session")
    return {"ok": True}


@router.get("/me", response_model=MeResponse)
def me(username: str = Depends(get_current_admin)) -> MeResponse:
    return MeResponse(authenticated=True, username=username)
