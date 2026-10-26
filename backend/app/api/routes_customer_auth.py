"""Customer accounts: signup, number + password login and password reset.

Reset codes go out as a simulated SMS: the code is in the response, as with
portal action OTPs. Anyone who knows a number can therefore reset its password.
That is fine for the demo but must change before real use."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.bss_http import bss_http_error
from app.api.deps import get_db, set_portal_session
from app.api.routes_me import portal_me
from app.api.schemas_me import OtpSms, PortalMe
from app.bss import otp, registration
from app.bss.accounts import mask_msisdn
from app.bss.clock import utc_now
from app.bss.errors import BssError, NoPendingAction, SubscriberNotFound
from app.models.telco import Actor, PlanType, Subscriber

router = APIRouter(prefix="/api/auth/customer", tags=["customer-auth"])
_NO_STORE = {"Cache-Control": "no-store"}
_RESET_PURPOSE = "password_reset"

Msisdn = Annotated[str, StringConstraints(pattern=r"^01\d{9}$")]
# bcrypt reads at most 72 bytes.
Password = Annotated[str, Field(min_length=8, max_length=72)]


class SignupRequest(BaseModel):
    full_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
    msisdn: Msisdn
    district: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=60)]
    plan_type: PlanType
    password: Password


class LoginRequest(BaseModel):
    msisdn: str
    password: str


class ResetStartRequest(BaseModel):
    msisdn: Msisdn


class ResetStart(BaseModel):
    reset_id: uuid.UUID
    otp: OtpSms


class ResetConfirmRequest(BaseModel):
    msisdn: Msisdn
    reset_id: uuid.UUID
    code: str
    new_password: Password


def _subscriber(db: Session, msisdn: str) -> Subscriber:
    sub = db.scalar(select(Subscriber).where(Subscriber.msisdn == msisdn))
    if sub is None:
        raise SubscriberNotFound()
    return sub


@router.post("/signup", response_model=PortalMe, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, response: Response, db: Session = Depends(get_db)) -> PortalMe:
    response.headers.update(_NO_STORE)
    try:
        sub = registration.create_subscriber(
            db,
            full_name=payload.full_name,
            msisdn=payload.msisdn,
            district=payload.district,
            plan_type=payload.plan_type,
            password=payload.password,
        )
    except BssError as e:
        db.rollback()
        raise bss_http_error(e)
    set_portal_session(response, sub.id)
    return portal_me(sub)


@router.post("/login", response_model=PortalMe)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> PortalMe:
    response.headers.update(_NO_STORE)
    sub = registration.authenticate(db, payload.msisdn, payload.password)
    if sub is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_credentials", "message": "Wrong number or password"},
        )
    set_portal_session(response, sub.id)
    return portal_me(sub)


@router.post("/reset/start", response_model=ResetStart)
def reset_start(
    payload: ResetStartRequest, response: Response, db: Session = Depends(get_db)
) -> ResetStart:
    response.headers.update(_NO_STORE)
    now = utc_now()
    reset_id = uuid.uuid4()
    try:
        sub = _subscriber(db, payload.msisdn)
        code = otp.issue(
            db,
            subscriber_id=sub.id,
            action_id=reset_id,
            purpose=_RESET_PURPOSE,
            payload={"msisdn": payload.msisdn},
            now=now,
            actor=Actor.portal,
            throttle=True,
        )
    except BssError as e:
        db.rollback()
        raise bss_http_error(e)
    expires_at = now + otp.OTP_TTL
    return ResetStart(
        reset_id=reset_id,
        otp=OtpSms(code=code, to=mask_msisdn(payload.msisdn), expires_at=expires_at),
    )


@router.post("/reset/confirm", response_model=PortalMe)
def reset_confirm(
    payload: ResetConfirmRequest, response: Response, db: Session = Depends(get_db)
) -> PortalMe:
    response.headers.update(_NO_STORE)
    try:
        sub = db.scalar(select(Subscriber).where(Subscriber.msisdn == payload.msisdn))
        if sub is None:
            raise NoPendingAction()
        otp.verify(
            db,
            subscriber_id=sub.id,
            action_id=payload.reset_id,
            purpose=_RESET_PURPOSE,
            payload={"msisdn": payload.msisdn},
            code=otp.normalise_code(payload.code),
            actor=Actor.portal,
            single_use=True,
        )
    except BssError as e:
        db.rollback()
        raise bss_http_error(e)
    registration.set_password(db, sub, payload.new_password)
    set_portal_session(response, sub.id)
    return portal_me(sub)
