"""Unauthenticated demo persona login: pick one of the five seeded personas
and get a customer `portal_session` cookie."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import PORTAL_COOKIE, get_db
from app.api.routes_me import portal_me
from app.api.schemas_me import PortalMe
from app.bss.accounts import mask_msisdn
from app.config import get_settings
from app.data.personas import PERSONA_HEADLINES
from app.models.telco import PlanType, Subscriber
from app.services.auth_service import create_access_token

router = APIRouter(prefix="/api/demo", tags=["demo"])
_NO_STORE = {"Cache-Control": "no-store"}


class PersonaCard(BaseModel):
    msisdn: str
    masked_msisdn: str
    full_name: str
    plan_type: PlanType
    district: str
    headline: str


class DemoLoginRequest(BaseModel):
    msisdn: str


@router.get("/personas", response_model=list[PersonaCard])
def personas(response: Response, db: Session = Depends(get_db)) -> list[PersonaCard]:
    response.headers.update(_NO_STORE)
    rows = {
        s.msisdn: s
        for s in db.scalars(select(Subscriber).where(Subscriber.msisdn.in_(PERSONA_HEADLINES)))
    }
    return [
        PersonaCard(
            msisdn=msisdn,
            masked_msisdn=mask_msisdn(msisdn),
            full_name=rows[msisdn].full_name,
            plan_type=rows[msisdn].plan_type,
            district=rows[msisdn].district,
            headline=headline,
        )
        for msisdn, headline in PERSONA_HEADLINES.items()
        if msisdn in rows
    ]


@router.post("/login", response_model=PortalMe)
def login(
    payload: DemoLoginRequest, response: Response, db: Session = Depends(get_db)
) -> PortalMe:
    response.headers.update(_NO_STORE)
    sub = None
    if payload.msisdn in PERSONA_HEADLINES:
        sub = db.scalar(select(Subscriber).where(Subscriber.msisdn == payload.msisdn))
    if sub is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown persona")
    settings = get_settings()
    response.set_cookie(
        PORTAL_COOKIE,
        create_access_token(str(sub.id), "customer"),
        httponly=True,
        samesite="lax",
        secure=False,  # set True once served over HTTPS
        max_age=settings.jwt_expire_minutes * 60,
    )
    return portal_me(sub)


@router.post("/logout")
def logout(response: Response) -> dict:
    response.headers.update(_NO_STORE)
    response.delete_cookie(PORTAL_COOKIE)
    return {"ok": True}
